"""Strict production-profile loading, validation, sealing and env mapping.

CTA-MODEL-001 separates two states:

* ``draft`` is safe to commit and may contain explicit ``null`` fields that can
  only be resolved on the accepted Mac mini from the private benchmark bundle;
* ``frozen`` is an immutable deployment contract. It rejects placeholders,
  missing hashes, non-loopback endpoints, model-identity ambiguity and missing
  resource measurements.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

from src.shared.security.hardening import is_loopback_host, is_loopback_url

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "model_profiles"
    / "production"
    / "cta_model_001.schema.json"
)
DEFAULT_PROFILE_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "model_profiles"
    / "production"
    / "cta_model_001.mac_mini_m4pro_24gb.draft.json"
)

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ENV_REF_RE = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")
_PLACEHOLDERS = {"todo", "tbd", "unknown", "replace-me", "placeholder", "local-model"}


class ProfileValidationError(ValueError):
    """Raised when a production model profile violates the contract."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid production model profile:\n- " + "\n- ".join(errors))


def _read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ProfileValidationError([f"{path}: root must be a JSON object"])
    return value


def load_profile(path: str | Path = DEFAULT_PROFILE_PATH) -> dict[str, Any]:
    """Load a profile without silently altering it."""
    return _read_json(path)


def load_schema(path: str | Path = SCHEMA_PATH) -> dict[str, Any]:
    return _read_json(path)


def _json_pointer(parts: list[Any]) -> str:
    if not parts:
        return "$"
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "$/" + "/".join(escaped)


def _schema_errors(profile: dict[str, Any], schema_path: str | Path) -> list[str]:
    schema = load_schema(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(profile), key=lambda item: list(item.absolute_path)):
        errors.append(f"{_json_pointer(list(error.absolute_path))}: {error.message}")
    return errors


def _get(profile: Mapping[str, Any], dotted: str) -> Any:
    value: Any = profile
    for part in dotted.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = value.strip().casefold()
        return not normalized or normalized in _PLACEHOLDERS or normalized.startswith("<")
    return False


def _origin(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}"


def _semantic_errors(profile: dict[str, Any], mode: str, *, require_integrity: bool) -> list[str]:
    errors: list[str] = []

    if mode not in {"draft", "frozen"}:
        return [f"unknown validation mode: {mode}"]
    expected_status = mode
    if profile.get("status") != expected_status:
        errors.append(f"status must be '{expected_status}' in {mode} mode")

    if _get(profile, "application.local_only_mode") is not True:
        errors.append("application.local_only_mode must be true")
    if _get(profile, "application.allow_cloud_llm") is not False:
        errors.append("application.allow_cloud_llm must be false")
    if _get(profile, "fallbacks.automatic_cloud_fallback") is not False:
        errors.append("fallbacks.automatic_cloud_fallback must be false")
    if _get(profile, "application.hybrid_ocr_vlm_enabled") is not False:
        errors.append("hybrid OCR→VLM must remain disabled for benchmark revision 20260801-091536")

    endpoints: list[tuple[str, dict[str, Any]]] = []
    for section in ("vision", "llm"):
        endpoint = _get(profile, f"{section}.endpoint")
        if not isinstance(endpoint, dict):
            continue
        endpoints.append((section, endpoint))
        base_url = str(endpoint.get("base_url") or "")
        host = str(endpoint.get("host") or "")
        if not is_loopback_url(base_url):
            errors.append(f"{section}.endpoint.base_url must be loopback-only: {base_url!r}")
        if not is_loopback_host(host):
            errors.append(f"{section}.endpoint.host must be loopback-only: {host!r}")
        parsed = urlparse(base_url)
        if parsed.port != endpoint.get("port"):
            errors.append(
                f"{section}.endpoint.port {endpoint.get('port')!r} does not match base_url {base_url!r}"
            )

        model_id = _get(profile, f"{section}.model.model_id")
        command = _get(profile, f"{section}.runtime.command")
        if isinstance(command, list) and model_id not in command:
            errors.append(f"{section}.runtime.command must contain the exact model_id")
        if isinstance(command, list) and host not in command:
            errors.append(f"{section}.runtime.command must contain the explicit loopback host")
        if isinstance(command, list) and str(endpoint.get("port")) not in command:
            errors.append(f"{section}.runtime.command must contain the explicit port")

    ports = [endpoint.get("port") for _, endpoint in endpoints]
    if len(ports) != len(set(ports)):
        errors.append("vision and llm endpoints must use distinct ports")

    if _get(profile, "vision.model.candidate_id") != "VLM-MLX-4B":
        errors.append("primary visual candidate must remain VLM-MLX-4B for this benchmark revision")
    if _get(profile, "llm.model.candidate_id") != "LLM-MLX-4B":
        errors.append("primary analytical candidate must remain LLM-MLX-4B for this benchmark revision")
    if _get(profile, "topology.benchmark_label") != "TOPOLOGY-U":
        errors.append("benchmark topology label must remain TOPOLOGY-U")

    if mode == "frozen":
        required_exact_fields = [
            "target_hardware.os_version",
            "target_hardware.os_build",
            "benchmark.artifact_manifest_sha256",
            "ocr.version",
            "ocr.language_data_sha256",
            "vision.runtime.version",
            "vision.runtime.python_version",
            "vision.model.source_revision",
            "vision.model.local_sha256",
            "vision.model.disk_bytes",
            "vision.limits.context_tokens",
            "vision.limits.max_image_bytes",
            "vision.limits.max_image_pixels",
            "llm.runtime.version",
            "llm.runtime.python_version",
            "llm.model.source_revision",
            "llm.model.local_sha256",
            "llm.model.disk_bytes",
            "llm.limits.context_tokens",
            "topology.operational_mode",
            "topology.reconciliation",
            "topology.load_unload_policy",
            "measured_envelope.cold_start_seconds",
            "measured_envelope.warm_p50_seconds",
            "measured_envelope.warm_p90_seconds",
            "measured_envelope.warm_max_seconds",
            "measured_envelope.peak_rss_bytes",
            "measured_envelope.peak_memory_pressure",
            "measured_envelope.swap_used_bytes",
            "measured_envelope.disk_footprint_bytes",
            "measured_envelope.concurrency_1_pass",
            "measured_envelope.concurrency_2_pass",
            "measured_envelope.shutdown_residual_processes",
        ]
        for dotted in required_exact_fields:
            if _is_placeholder(_get(profile, dotted)):
                errors.append(f"{dotted} must be populated before the profile is frozen")

        for dotted in (
            "benchmark.artifact_manifest_sha256",
            "ocr.language_data_sha256",
            "vision.model.local_sha256",
            "llm.model.local_sha256",
        ):
            value = _get(profile, dotted)
            if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
                errors.append(f"{dotted} must be a lowercase SHA-256 digest")

        for dotted in ("vision.model.source_revision", "llm.model.source_revision"):
            value = _get(profile, dotted)
            if not isinstance(value, str) or len(value.strip()) < 7:
                errors.append(f"{dotted} must contain an exact source revision")

        if _get(profile, "measured_envelope.concurrency_1_pass") is not True:
            errors.append("concurrency=1 must pass before freezing")
        if _get(profile, "measured_envelope.concurrency_2_pass") is not True:
            errors.append("concurrency=2 must pass before freezing")
        if _get(profile, "measured_envelope.shutdown_residual_processes") != 0:
            errors.append("frozen profile requires zero residual model processes after shutdown")

        if require_integrity:
            digest = _get(profile, "integrity.profile_sha256")
            sealed_at = _get(profile, "integrity.sealed_at_utc")
            if not isinstance(digest, str) or not _HASH_RE.fullmatch(digest):
                errors.append("integrity.profile_sha256 must be populated in frozen mode")
            if _is_placeholder(sealed_at):
                errors.append("integrity.sealed_at_utc must be populated in frozen mode")
            if isinstance(digest, str) and _HASH_RE.fullmatch(digest):
                actual = canonical_profile_sha256(profile)
                if actual != digest:
                    errors.append(
                        f"integrity.profile_sha256 mismatch: expected {digest}, calculated {actual}"
                    )

    return errors


def validate_profile(
    profile: dict[str, Any],
    *,
    mode: str | None = None,
    schema_path: str | Path = SCHEMA_PATH,
    raise_on_error: bool = True,
    require_integrity: bool = True,
) -> list[str]:
    """Validate schema plus semantic production constraints."""
    resolved_mode = mode or str(profile.get("status") or "draft")
    errors = _schema_errors(profile, schema_path)
    errors.extend(_semantic_errors(profile, resolved_mode, require_integrity=require_integrity))
    deduplicated = list(dict.fromkeys(errors))
    if deduplicated and raise_on_error:
        raise ProfileValidationError(deduplicated)
    return deduplicated


def _canonical_payload(profile: dict[str, Any]) -> bytes:
    value = copy.deepcopy(profile)
    integrity = value.setdefault("integrity", {})
    integrity["profile_sha256"] = None
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def canonical_profile_sha256(profile: dict[str, Any]) -> str:
    """Hash a profile while excluding only its self-referential digest field."""
    return hashlib.sha256(_canonical_payload(profile)).hexdigest()


def seal_profile(profile: dict[str, Any], *, sealed_at: str | None = None) -> dict[str, Any]:
    """Return a frozen, integrity-bound copy of a fully populated draft."""
    frozen = copy.deepcopy(profile)
    frozen["status"] = "frozen"
    frozen.setdefault("integrity", {})["sealed_at_utc"] = sealed_at or datetime.now(
        timezone.utc
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    frozen["integrity"]["profile_sha256"] = None
    validate_profile(frozen, mode="frozen", require_integrity=False)
    frozen["integrity"]["profile_sha256"] = canonical_profile_sha256(frozen)
    validate_profile(frozen, mode="frozen", require_integrity=True)
    return frozen


def render_application_env(profile: dict[str, Any]) -> dict[str, str]:
    """Map the frozen contract to the existing CTA application settings."""
    validate_profile(profile, mode=str(profile.get("status") or "draft"), require_integrity=False)
    application = profile["application"]
    vision = profile["vision"]
    llm = profile["llm"]
    env: dict[str, str] = {
        "CTA_LOCAL_ONLY_MODE": "true",
        "CTA_ALLOW_CLOUD_LLM": "false",
        "CTA_LLM_PROVIDER": application["llm_provider"],
        "CTA_LLM_MODEL": llm["model"]["model_id"],
        "CTA_LLM_BASE_URL": llm["endpoint"]["base_url"],
        "CTA_LLM_TIMEOUT_SECONDS": str(application["request_timeout_seconds"]),
        "CTA_VISION_PROVIDER": application["vision_provider"],
        "CTA_ENABLE_LOCAL_OCR": "false",
        "CTA_ENABLE_LOCAL_VLM": "true",
        "CTA_VISION_API_STYLE": application["vision_api_style"],
        "CTA_VISION_MODEL": vision["model"]["model_id"],
        "CTA_VISION_BASE_URL": vision["endpoint"]["base_url"],
        "CTA_VISION_TIMEOUT_SECONDS": str(application["request_timeout_seconds"]),
    }
    if vision["limits"].get("max_image_bytes") is not None:
        env["CTA_VISION_MAX_IMAGE_BYTES"] = str(vision["limits"]["max_image_bytes"])
    if vision["limits"].get("max_image_pixels") is not None:
        env["CTA_VISION_MAX_IMAGE_PIXELS"] = str(vision["limits"]["max_image_pixels"])
    return env


def env_text(profile: dict[str, Any]) -> str:
    env = render_application_env(profile)
    lines = [
        "# Generated from CTA-MODEL-001. Do not edit values independently.",
        f"# profile_id={profile['profile_id']}",
        f"# profile_sha256={profile.get('integrity', {}).get('profile_sha256') or 'DRAFT'}",
    ]
    lines.extend(f"{key}={env[key]}" for key in sorted(env))
    return "\n".join(lines) + "\n"


def parse_env_text(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ProfileValidationError([f"invalid env line: {raw_line!r}"])
        result[key.strip()] = value.strip()
    return result


def validate_application_env(profile: dict[str, Any], env: Mapping[str, str]) -> list[str]:
    expected = render_application_env(profile)
    errors: list[str] = []
    for key, expected_value in expected.items():
        actual = env.get(key)
        if actual != expected_value:
            errors.append(f"{key}: expected {expected_value!r}, got {actual!r}")
    return errors


def resolve_command(command: list[str], env: Mapping[str, str]) -> list[str]:
    """Resolve only whole-token ${VAR} references; partial shell expansion is forbidden."""
    resolved: list[str] = []
    errors: list[str] = []
    for token in command:
        match = _ENV_REF_RE.fullmatch(token)
        if not match:
            resolved.append(token)
            continue
        name = match.group(1)
        value = env.get(name)
        if not value:
            errors.append(f"required runtime environment variable is missing: {name}")
        else:
            resolved.append(value)
    if errors:
        raise ProfileValidationError(errors)
    return resolved


def model_identity_url(server: Mapping[str, Any]) -> str:
    endpoint = server["endpoint"]
    return _origin(endpoint["base_url"]) + endpoint["models_path"]
