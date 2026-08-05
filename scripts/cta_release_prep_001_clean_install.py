#!/usr/bin/env python3
"""Clean-machine synthetic install and rollback rehearsal for CTA-RELEASE-PREP-001."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Sequence

RELEASE_ID = "CTA-RELEASE-PREP-001"


class CleanInstallError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_bundle(bundle: Path, destination: Path) -> Path:
    if bundle.is_dir():
        target = destination / bundle.name
        shutil.copytree(bundle, target)
        return target
    if not bundle.is_file() or bundle.suffix.lower() != ".zip":
        raise CleanInstallError(f"bundle not found or not a ZIP: {bundle}")
    roots: set[str] = set()
    with zipfile.ZipFile(bundle) as archive:
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts:
                raise CleanInstallError(f"unsafe ZIP member: {info.filename}")
            if not info.is_dir():
                if len(path.parts) < 2:
                    raise CleanInstallError(f"ZIP member outside root: {info.filename}")
                roots.add(path.parts[0])
        if len(roots) != 1:
            raise CleanInstallError(f"ZIP must contain one root directory, found {sorted(roots)}")
        archive.extractall(destination)
    return destination / next(iter(roots))


def _run(label: str, command: Sequence[str], *, cwd: Path, env: dict[str, str], records: list[dict]) -> None:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=900,
        check=False,
    )
    records.append({"step": label, "returncode": completed.returncode, "status": "PASS" if completed.returncode == 0 else "FAIL"})
    if completed.returncode != 0:
        tail = "\n".join(completed.stdout.splitlines()[-80:])
        raise CleanInstallError(f"{label} failed with exit code {completed.returncode}:\n{tail}")


def _create_venv(
    python_executable: str | Path,
    venv_dir: Path,
    *,
    cwd: Path,
    env: dict[str, str],
    records: list[dict],
) -> Path:
    """Create a pip-enabled virtual environment through the venv CLI.

    The ``python -m venv`` subprocess form is used instead of the in-process
    venv builder API: on uv-managed CPython builds that API spawns the venv
    interpreter symlink whose rpath resolves against the venv directory, so
    dyld aborts with "Library not loaded: libpython3.11.dylib".
    """
    _run(
        "create-venv",
        [str(python_executable), "-m", "venv", str(venv_dir)],
        cwd=cwd,
        env=env,
        records=records,
    )
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _validation_env(workspace: Path) -> dict[str, str]:
    data_root = workspace / ".release-validation"
    for name in ("db", "storage", "exports", "backups"):
        (data_root / name).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "CTA_ENV": "onprem-validation",
            "CTA_HOST": "127.0.0.1",
            "CTA_PORT": "18080",
            "CTA_PUBLIC_BASE_URL": "http://127.0.0.1:18080",
            "CTA_BASE_URL": "http://127.0.0.1:18080",
            "CTA_LOCAL_ONLY_MODE": "true",
            "CTA_ALLOW_CLOUD_LLM": "false",
            "CTA_LLM_PROVIDER": "stub",
            "CTA_VISION_PROVIDER": "stub",
            "CTA_ENABLE_LOCAL_OCR": "false",
            "CTA_ENABLE_LOCAL_VLM": "false",
            "CTA_ENABLE_AUTH": "true",
            "CTA_ENABLE_ADMIN": "true",
            "CTA_ENABLE_PROJECTS": "true",
            "CTA_ENABLE_BRANDBOOKS": "true",
            "CTA_ENABLE_ADVANCED_EXPORTS": "true",
            "CTA_SECRET_KEY": secrets.token_urlsafe(48),
            "CTA_BOOTSTRAP_ADMIN_EMAIL": "release-validator@example.invalid",
            "CTA_BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(32),
            "CTA_BOOTSTRAP_ADMIN_NAME": "Release Validator",
            "CTA_TRUSTED_HOSTS": "localhost,127.0.0.1,testserver",
            "CTA_CORS_ALLOWED_ORIGINS": "",
            "CTA_SECURITY_FAIL_CLOSED": "true",
            "CTA_SECURITY_HEADERS_ENABLED": "true",
            "CTA_DATABASE_URL": f"sqlite:///{(data_root / 'db/creative_test_agent.db').as_posix()}",
            "CTA_STORAGE_ROOT": str(data_root / "storage"),
            "CTA_EXPORTS_ROOT": str(data_root / "exports"),
            "CTA_BACKUP_ROOT": str(data_root / "backups"),
            "CTA_BACKUP_INCLUDE_UPLOADS": "true",
            "CTA_BACKUP_INCLUDE_EXPORTS": "true",
            "CTA_ENABLE_PROMPT_TRACING": "true",
            "CTA_PROMPT_TRACE_STORE_FULL": "false",
        }
    )
    return env


def _python_snippet(python: Path, code: str, *, cwd: Path, env: dict[str, str], records: list[dict], label: str) -> None:
    _run(label, [str(python), "-c", code], cwd=cwd, env=env, records=records)


def run_clean_install(bundle: Path, evidence_path: Path | None = None, *, keep_workspace: bool = False) -> dict:
    records: list[dict] = []
    temp = tempfile.TemporaryDirectory(prefix="cta-release-clean-install-")
    temp_root = Path(temp.name)
    try:
        workspace = _extract_bundle(bundle.resolve(), temp_root)
        venv_dir = temp_root / ".venv"
        python = _create_venv(
            sys.executable,
            venv_dir,
            cwd=workspace,
            env=os.environ.copy(),
            records=records,
        )
        env = _validation_env(workspace)
        env["VIRTUAL_ENV"] = str(venv_dir)
        env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")

        _run(
            "validate-release-bundle",
            [
                str(python),
                "scripts/cta_release_prep_001.py",
                "--project-root",
                ".",
                "--config",
                "config/release/cta_release_prep_001.json",
                "validate",
                "--bundle",
                ".",
            ],
            cwd=workspace,
            env=env,
            records=records,
        )
        _run("upgrade-pip", [str(python), "-m", "pip", "install", "--upgrade", "pip"], cwd=workspace, env=env, records=records)
        _run("install-project", [str(python), "-m", "pip", "install", ".[dev]"], cwd=workspace, env=env, records=records)
        _run("compile-source", [str(python), "-m", "compileall", "-q", "src", "scripts"], cwd=workspace, env=env, records=records)
        _run("model-registry", [str(python), "scripts/check_model_registry.py"], cwd=workspace, env=env, records=records)
        _run("migrations-upgrade", [str(python), "scripts/run_migrations.py"], cwd=workspace, env=env, records=records)
        _run("migrations-check", [str(python), "scripts/check_migrations.py"], cwd=workspace, env=env, records=records)
        _run("closed-loop-check", [str(python), "scripts/check_closed_loop.py"], cwd=workspace, env=env, records=records)
        legacy_readiness_env = dict(env)
        legacy_readiness_env.update({"CTA_ENABLE_AUTH": "false", "CTA_ENABLE_PROJECTS": "false"})
        _run(
            "server-readiness-legacy-default-profile",
            [str(python), "scripts/check_server_readiness.py"],
            cwd=workspace,
            env=legacy_readiness_env,
            records=records,
        )
        onprem_settings = """
import os
from src.shared.config.settings import get_settings
settings = get_settings()
assert settings.host == '127.0.0.1', settings.host
assert settings.enable_auth is True, settings.enable_auth
assert settings.enable_projects is True, settings.enable_projects
assert settings.local_only_mode is True, settings.local_only_mode
assert settings.allow_cloud_llm is False, settings.allow_cloud_llm
assert os.environ.get('CTA_SECURITY_FAIL_CLOSED', '').lower() == 'true'
assert os.environ.get('CTA_SECURITY_HEADERS_ENABLED', '').lower() == 'true'
"""
        _python_snippet(python, onprem_settings, cwd=workspace, env=env, records=records, label="onprem-settings-readiness")

        http_smoke = """
from fastapi.testclient import TestClient
from src.main import app
with TestClient(app) as client:
    response = client.get('/health')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get('status') in {'ok', 'healthy'}, body
"""
        _python_snippet(python, http_smoke, cwd=workspace, env=env, records=records, label="http-health-smoke")

        db_path = workspace / ".release-validation/db/creative_test_agent.db"
        create_sentinel = f"""
import sqlite3
path = {str(db_path)!r}
connection = sqlite3.connect(path)
connection.execute('CREATE TABLE IF NOT EXISTS release_rollback_sentinel (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
connection.execute("INSERT OR REPLACE INTO release_rollback_sentinel(id, value) VALUES (1, 'before-backup')")
connection.commit()
connection.close()
"""
        _python_snippet(python, create_sentinel, cwd=workspace, env=env, records=records, label="rollback-seed")
        backup_path = workspace / ".release-validation/backups/release-rollback.zip"
        _run("rollback-backup", [str(python), "scripts/backup_data.py", str(backup_path)], cwd=workspace, env=env, records=records)
        mutate_sentinel = f"""
import sqlite3
connection = sqlite3.connect({str(db_path)!r})
connection.execute("UPDATE release_rollback_sentinel SET value='after-backup' WHERE id=1")
connection.commit()
connection.close()
"""
        _python_snippet(python, mutate_sentinel, cwd=workspace, env=env, records=records, label="rollback-mutate")
        _run(
            "rollback-restore",
            [str(python), "scripts/restore_data.py", str(backup_path), "--force", "--skip-pre-restore-backup"],
            cwd=workspace,
            env=env,
            records=records,
        )
        verify_sentinel = f"""
import sqlite3
connection = sqlite3.connect({str(db_path)!r})
value = connection.execute('SELECT value FROM release_rollback_sentinel WHERE id=1').fetchone()[0]
connection.close()
assert value == 'before-backup', value
"""
        _python_snippet(python, verify_sentinel, cwd=workspace, env=env, records=records, label="rollback-verify")

        manifest = json.loads((workspace / "release-manifest.json").read_text(encoding="utf-8"))
        result = {
            "release_id": RELEASE_ID,
            "app_version": manifest.get("app_version"),
            "bundle_sha256": _sha256(bundle) if bundle.is_file() else None,
            "clean_environment": True,
            "network_used_for_dependency_install": True,
            "local_only_runtime": True,
            "synthetic_data_only": True,
            "rollback_rehearsal": "PASS",
            "steps": records,
            "status": "PASS",
        }
        if evidence_path:
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        if keep_workspace:
            retained = Path.cwd() / "artifacts/local-acceptance/CTA-RELEASE-PREP-001/clean-install-workspace"
            if retained.exists():
                shutil.rmtree(retained)
            retained.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(workspace, retained)
            result["workspace_retained"] = True
        return result
    finally:
        temp.cleanup()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--keep-workspace", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_clean_install(args.bundle, args.evidence, keep_workspace=args.keep_workspace)
    except (CleanInstallError, subprocess.SubprocessError, OSError) as exc:
        print(f"{RELEASE_ID} clean install: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
