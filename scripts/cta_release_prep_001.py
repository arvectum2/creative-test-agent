#!/usr/bin/env python3
"""Deterministic on-prem bundle builder/validator for CTA-RELEASE-PREP-001."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

RELEASE_ID = "CTA-RELEASE-PREP-001"
CONFIG = "config/release/cta_release_prep_001.json"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
MAX_FILE = 50 * 1024 * 1024
META = ("release-manifest.json", "sbom.cdx.json", "dependency-export.txt", "SHA256SUMS")
FORBIDDEN_NAMES = {".env", ".env.server", ".env.local", "id_rsa", "id_ed25519", "credentials.json", "secrets.json"}
FORBIDDEN_SUFFIXES = {".gguf", ".safetensors", ".onnx", ".pt", ".pth", ".ckpt", ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"}
FORBIDDEN_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache", "node_modules", "artifacts", "logs", "weights"}
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("OpenAI-style token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)
LOCAL_PATHS = (
    re.compile(r"(?<![A-Za-z0-9_])/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"(?<![A-Za-z0-9_])/home/[A-Za-z0-9._-]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
)


class ReleaseError(RuntimeError):
    pass


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseError(f"JSON root must be an object: {path}")
    return value


def load_config(root, config_path=CONFIG):
    path = Path(config_path)
    if not path.is_absolute():
        path = Path(root) / path
    config = read_json(path)
    required = {"schema_version", "release_id", "app_version", "bundle_name", "source_date_epoch", "required_files", "required_directories", "operational_docs", "frozen_model_profile"}
    missing = sorted(required - config.keys())
    if missing:
        raise ReleaseError("release config missing: " + ", ".join(missing))
    if config["release_id"] != RELEASE_ID or config["schema_version"] != "1.0.0":
        raise ReleaseError("unsupported release id/schema")
    return config


def relpath(value):
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
        raise ReleaseError(f"unsafe relative path: {value}")
    return str(path)


def forbidden_path(rel):
    path = PurePosixPath(rel)
    parts = {part.lower() for part in path.parts}
    if parts & {part.lower() for part in FORBIDDEN_PARTS}:
        return "forbidden directory"
    if path.name.lower() in {name.lower() for name in FORBIDDEN_NAMES}:
        return "secret/config file"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return "forbidden file type"
    return None


def validate_bytes(rel, data):
    if len(data) > MAX_FILE:
        raise ReleaseError(f"payload exceeds 50 MiB: {rel}")
    reason = forbidden_path(rel)
    if reason:
        raise ReleaseError(f"forbidden path ({reason}): {rel}")
    if b"\x00" in data:
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return
    findings = [f"{rel}: possible {name}" for name, pattern in SECRET_PATTERNS if pattern.search(text)]
    findings += [f"{rel}: absolute local user path" for pattern in LOCAL_PATHS if pattern.search(text)]
    if findings:
        raise ReleaseError("payload scan failed:\n- " + "\n- ".join(findings))


def collect_files(root, config):
    root = Path(root)
    selected = set()

    def add_file(value):
        rel = relpath(value)
        path = root / rel
        if not path.is_file():
            raise ReleaseError(f"required file missing: {rel}")
        if forbidden_path(rel):
            raise ReleaseError(f"required file is forbidden: {rel}")
        selected.add(rel)

    for item in config["required_files"] + config["operational_docs"]:
        add_file(item)
    for item in config["required_directories"]:
        rel_dir = relpath(item)
        directory = root / rel_dir
        if not directory.is_dir():
            raise ReleaseError(f"required directory missing: {rel_dir}")
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not path.is_symlink():
                rel = path.relative_to(root).as_posix()
                if not forbidden_path(rel):
                    selected.add(rel)
    return sorted(selected)


def app_version(root):
    text = (Path(root) / "src/shared/version.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise ReleaseError("APP_VERSION not found")
    return match.group(1)


def parse_req(raw):
    match = re.match(r"^([A-Za-z0-9_.-]+)(.*)$", raw.strip())
    return {"name": match.group(1), "version_spec": match.group(2).strip()} if match else {"name": raw.strip(), "version_spec": ""}


def dependencies(root, config):
    root = Path(root)
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    result = []
    for raw in pyproject.get("project", {}).get("dependencies", []):
        item = parse_req(str(raw)); item.update(scope="application", source="pyproject.toml"); result.append(item)
    profile_cfg = config["frozen_model_profile"]
    profile = read_json(root / profile_cfg["path"])
    runtime = (
        ("model_runtime_vision", profile.get("vision", {}).get("runtime", {}).get("version")),
        ("model_runtime_llm", profile.get("llm", {}).get("runtime", {}).get("version")),
        ("model_runtime_ocr", profile.get("ocr", {}).get("version")),
    )
    for scope, raw in runtime:
        if raw:
            normalized = str(raw).replace(" ", "==", 1) if scope.endswith("ocr") and "==" not in str(raw) else str(raw)
            item = parse_req(normalized); item.update(scope=scope, source=profile_cfg["path"]); result.append(item)
    for req_path in profile_cfg.get("runtime_requirement_files", []):
        path = root / req_path
        if not path.is_file():
            raise ReleaseError(f"runtime dependency contract missing: {req_path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                item = parse_req(line); item.update(scope="model_runtime_lock", source=req_path); result.append(item)
    deduped = {(item["name"].lower(), item["version_spec"], item["scope"]): item for item in result}
    return sorted(deduped.values(), key=lambda item: (item["scope"], item["name"].lower(), item["version_spec"]))


def model_summary(root, config):
    cfg = config["frozen_model_profile"]
    path = Path(root) / cfg["path"]
    file_sha = sha_file(path)
    if file_sha != cfg["expected_file_sha256"]:
        raise ReleaseError(f"frozen profile file hash mismatch: {file_sha}")
    profile = read_json(path)
    internal = profile.get("integrity", {}).get("profile_sha256")
    if internal != cfg["expected_internal_profile_sha256"]:
        raise ReleaseError(f"frozen profile internal hash mismatch: {internal}")
    def model(role):
        section = profile.get(role, {})
        return {"model_id": section.get("model", {}).get("model_id"), "source_revision": section.get("model", {}).get("source_revision"), "artifact_sha256": section.get("model", {}).get("local_sha256"), "weight_included": False}
    return {"path": cfg["path"], "file_sha256": file_sha, "internal_profile_sha256": internal, "profile_id": profile.get("profile_id"), "status": profile.get("status"), "target_platform": profile.get("target_hardware", {}).get("platform"), "vision": model("vision"), "llm": model("llm")}


def env_values(data):
    values = {}
    for line in data.decode().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1); values[key.strip()] = value.strip()
    return values


def validate_env(data, config):
    values = env_values(data)
    required = {"CTA_LOCAL_ONLY_MODE": "true", "CTA_ALLOW_CLOUD_LLM": "false", "CTA_ENABLE_AUTH": "true", "CTA_SECURITY_FAIL_CLOSED": "true", "CTA_SECURITY_HEADERS_ENABLED": "true", "CTA_HOST": "127.0.0.1"}
    required.update({str(k): str(v) for k, v in config.get("required_env", {}).items()})
    failures = [f"{key}={values.get(key)!r}, expected {expected!r}" for key, expected in required.items() if values.get(key, "").lower() != expected.lower()]
    for key in config.get("required_secret_placeholders", []):
        if "REQUIRED_CHANGE_ME" not in values.get(key, ""):
            failures.append(f"{key} lacks REQUIRED_CHANGE_ME placeholder")
    if values.get("CTA_CORS_ALLOWED_ORIGINS", ""):
        failures.append("CTA_CORS_ALLOWED_ORIGINS must be empty")
    if failures:
        raise ReleaseError("fail-closed env invalid:\n- " + "\n- ".join(failures))


def sbom(version, revision, deps):
    components = []
    for dep in deps:
        item = {"type": "library", "name": dep["name"], "properties": [{"name": "cta:scope", "value": dep["scope"]}, {"name": "cta:declared_version_spec", "value": dep["version_spec"]}, {"name": "cta:source", "value": dep["source"]}]}
        if dep["version_spec"].startswith("=="):
            item["version"] = dep["version_spec"][2:]
        components.append(item)
    return {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1, "metadata": {"component": {"type": "application", "name": "creative-test-agent", "version": version, "properties": [{"name": "cta:release_id", "value": RELEASE_ID}, {"name": "cta:source_revision", "value": revision}, {"name": "cta:dependency_resolution", "value": "declared_specs_plus_frozen_runtime_pins"}]}}, "components": components}


def write(path, data, executable=False):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data); path.chmod(0o755 if executable else 0o644)


def deterministic_zip(bundle_root, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in Path(bundle_root).rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(path.relative_to(Path(bundle_root).parent).as_posix(), ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED; info.create_system = 3
            mode = 0o755 if os.access(path, os.X_OK) else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, path.read_bytes())


def build_release(root, config_path=CONFIG, output_dir=None, source_revision="UNSPECIFIED"):
    root = Path(root).resolve(); config = load_config(root, config_path)
    version = app_version(root)
    if version != config["app_version"]:
        raise ReleaseError(f"version mismatch: source={version}, config={config['app_version']}")
    revision = source_revision if source_revision != "UNSPECIFIED" else os.getenv("GITHUB_SHA") or os.getenv("CTA_SOURCE_REVISION") or "UNSPECIFIED"
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}|UNSPECIFIED", revision):
        raise ReleaseError("source revision must be a Git SHA or UNSPECIFIED")
    release_root = Path(output_dir or root / "data/release/cta-release-prep-001").resolve()
    bundle_root = release_root / config["bundle_name"]; zip_path = release_root / f"{config['bundle_name']}.zip"
    if bundle_root.exists(): shutil.rmtree(bundle_root)
    release_root.mkdir(parents=True, exist_ok=True); zip_path.unlink(missing_ok=True); zip_path.with_suffix(".zip.sha256").unlink(missing_ok=True)
    payload = []
    for rel in collect_files(root, config):
        data = (root / rel).read_bytes(); validate_bytes(rel, data); write(bundle_root / rel, data, rel.startswith("scripts/") and data.startswith(b"#!"))
        payload.append({"path": rel, "sha256": sha_bytes(data), "size": len(data)})
    validate_env((bundle_root / config["environment_template"]).read_bytes(), config)
    deps = dependencies(root, config); profile = model_summary(root, config)
    dep_text = "\n".join(f"{item['scope']}\t{item['name']}{item['version_spec']}\t{item['source']}" for item in deps) + "\n"
    manifest = {"schema_version": "1.0.0", "release_id": RELEASE_ID, "app_version": version, "bundle_name": config["bundle_name"], "source_revision": revision, "source_date_epoch": int(config["source_date_epoch"]), "execution_mode": "GITHUB+HYBRID", "installation_boundary": "client installation is CTA-DEPLOY-001", "policy": {"local_only": True, "cloud_fallback": False, "authentication_required": True, "security_fail_closed": True, "model_weights_included": False, "client_data_included": False}, "frozen_model_profile": profile, "dependencies": {"inventory_count": len(deps), "sbom_path": "sbom.cdx.json", "export_path": "dependency-export.txt", "application_dependencies_are_declared_specs": True, "model_runtime_dependencies_include_exact_pins": True}, "payload": payload, "operational_docs": sorted(config["operational_docs"])}
    write(bundle_root / "dependency-export.txt", dep_text.encode()); write(bundle_root / "sbom.cdx.json", canonical(sbom(version, revision, deps))); write(bundle_root / "release-manifest.json", canonical(manifest))
    sums = [f"{sha_file(path)}  {path.relative_to(bundle_root).as_posix()}" for path in sorted(item for item in bundle_root.rglob("*") if item.is_file() and item.name != "SHA256SUMS")]
    write(bundle_root / "SHA256SUMS", ("\n".join(sums) + "\n").encode()); deterministic_zip(bundle_root, zip_path)
    zip_sha = sha_file(zip_path); sha_path = zip_path.with_suffix(".zip.sha256"); write(sha_path, f"{zip_sha}  {zip_path.name}\n".encode())
    validate_release(bundle_root, root / str(config_path), root)
    return {"bundle_dir": str(bundle_root), "zip_path": str(zip_path), "zip_sha256": zip_sha, "sha256_path": str(sha_path)}


def extract_zip(bundle, target):
    with zipfile.ZipFile(bundle) as archive:
        roots = set()
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ReleaseError(f"unsafe ZIP member: {info.filename}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ReleaseError(f"symlink in ZIP: {info.filename}")
            if not info.is_dir():
                if len(path.parts) < 2: raise ReleaseError(f"member outside bundle root: {info.filename}")
                roots.add(path.parts[0])
        if len(roots) != 1: raise ReleaseError(f"ZIP must contain one root, found {sorted(roots)}")
        archive.extractall(target)
    return Path(target) / next(iter(roots))


def validate_sums(bundle_root):
    path = bundle_root / "SHA256SUMS"
    if not path.is_file(): raise ReleaseError("SHA256SUMS missing")
    expected = {}
    for line in path.read_text().splitlines():
        if not line: continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match: raise ReleaseError(f"invalid SHA256SUMS line: {line}")
        expected[relpath(match.group(2))] = match.group(1)
    actual = sorted(path.relative_to(bundle_root).as_posix() for path in bundle_root.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    if sorted(expected) != actual: raise ReleaseError("SHA256SUMS file set mismatch")
    for rel, digest in expected.items():
        if sha_file(bundle_root / rel) != digest: raise ReleaseError(f"checksum mismatch: {rel}")


def validate_release(bundle, config_path=None, project_root=None):
    bundle = Path(bundle).resolve(); temp = None
    if bundle.is_file():
        temp = tempfile.TemporaryDirectory(prefix="cta-release-validate-"); bundle_root = extract_zip(bundle, temp.name)
    elif bundle.is_dir(): bundle_root = bundle
    else: raise ReleaseError(f"bundle not found: {bundle}")
    try:
        for name in META:
            if not (bundle_root / name).is_file(): raise ReleaseError(f"metadata missing: {name}")
        validate_sums(bundle_root); manifest = read_json(bundle_root / "release-manifest.json")
        if manifest.get("release_id") != RELEASE_ID: raise ReleaseError("wrong release_id")
        policy = manifest.get("policy", {})
        if policy.get("model_weights_included") is not False or policy.get("client_data_included") is not False: raise ReleaseError("unsafe manifest policy")
        declared = {}
        for item in manifest.get("payload", []): declared[relpath(item["path"])] = (item["sha256"], int(item["size"]))
        paths = [path for path in bundle_root.rglob("*") if path.is_file()]
        if any(path.is_symlink() for path in paths): raise ReleaseError("symlinks forbidden")
        for rel, (digest, size) in declared.items():
            data = (bundle_root / rel).read_bytes(); validate_bytes(rel, data)
            if sha_bytes(data) != digest or len(data) != size: raise ReleaseError(f"manifest mismatch: {rel}")
        for path in paths: validate_bytes(path.relative_to(bundle_root).as_posix(), path.read_bytes())
        bom = read_json(bundle_root / "sbom.cdx.json")
        if bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != "1.5" or not bom.get("components"): raise ReleaseError("invalid SBOM")
        config = load_config(Path(project_root or ".").resolve(), config_path) if config_path else {}
        env_rel = config.get("environment_template", ".env.onprem.example")
        if not (bundle_root / env_rel).is_file(): raise ReleaseError(f"env template missing: {env_rel}")
        validate_env((bundle_root / env_rel).read_bytes(), config)
        profile = manifest.get("frozen_model_profile", {}); profile_path = bundle_root / relpath(profile.get("path", ""))
        if not profile_path.is_file() or sha_file(profile_path) != profile.get("file_sha256"): raise ReleaseError("frozen model profile mismatch")
        return {"release_id": RELEASE_ID, "app_version": manifest["app_version"], "files": len(paths), "payload_files": len(declared), "sbom_components": len(bom["components"]), "status": "PASS"}
    finally:
        if temp: temp.cleanup()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--project-root", default="."); parser.add_argument("--config", default=CONFIG)
    subs = parser.add_subparsers(dest="command", required=True)
    build = subs.add_parser("build"); build.add_argument("--output-dir"); build.add_argument("--source-revision", default="UNSPECIFIED")
    validate = subs.add_parser("validate"); validate.add_argument("--bundle", required=True)
    args = parser.parse_args(argv)
    try:
        result = build_release(Path(args.project_root), args.config, Path(args.output_dir) if getattr(args, "output_dir", None) else None, getattr(args, "source_revision", "UNSPECIFIED")) if args.command == "build" else validate_release(Path(args.bundle), Path(args.project_root) / args.config, Path(args.project_root))
    except ReleaseError as exc:
        print(f"{RELEASE_ID}: FAIL: {exc}", file=sys.stderr); return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
