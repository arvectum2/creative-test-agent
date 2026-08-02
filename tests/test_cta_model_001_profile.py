from __future__ import annotations

import pytest

from src.shared.model_profile.profile import (
    DEFAULT_PROFILE_PATH,
    ProfileValidationError,
    canonical_profile_sha256,
    env_text,
    load_profile,
    parse_env_text,
    render_application_env,
    resolve_command,
    seal_profile,
    validate_application_env,
    validate_profile,
)


def _fully_populated_profile() -> dict:
    profile = load_profile(DEFAULT_PROFILE_PATH)
    profile["target_hardware"].update(os_version="26.6", os_build="25G84")
    profile["benchmark"]["artifact_manifest_sha256"] = "a" * 64
    profile["ocr"].update(
        version="tesseract 5.5.3",
        language_data_sha256="b" * 64,
    )
    for section, revision, digest in (
        ("vision", "0123456789abcdef0123456789abcdef01234567", "c" * 64),
        ("llm", "89abcdef0123456789abcdef0123456789abcdef", "d" * 64),
    ):
        profile[section]["runtime"].update(version="1.2.3", python_version="3.14.0")
        profile[section]["model"].update(
            source_revision=revision,
            local_sha256=digest,
            disk_bytes=4_000_000_000,
        )
        profile[section]["limits"]["context_tokens"] = 8192
    profile["vision"]["limits"].update(
        max_image_bytes=25 * 1024 * 1024,
        max_image_pixels=16_000_000,
    )
    profile["topology"].update(
        operational_mode="dual_server_resident",
        reconciliation=(
            "TOPOLOGY-U selects the unified analytical path while the accepted "
            "application deployment keeps separate loopback VLM and LLM servers resident."
        ),
        load_unload_policy="Load both servers before the operator session and stop both after it.",
    )
    profile["measured_envelope"].update(
        cold_start_seconds=14.0,
        warm_p50_seconds=4.1,
        warm_p90_seconds=5.0,
        warm_max_seconds=6.2,
        peak_rss_bytes=9_000_000_000,
        peak_memory_pressure="normal",
        swap_used_bytes=0,
        disk_footprint_bytes=8_000_000_000,
        concurrency_1_pass=True,
        concurrency_2_pass=True,
        shutdown_residual_processes=0,
    )
    return profile


def test_committed_draft_is_schema_valid():
    profile = load_profile(DEFAULT_PROFILE_PATH)
    assert validate_profile(profile, mode="draft", raise_on_error=False) == []


def test_draft_is_not_accepted_as_frozen():
    profile = load_profile(DEFAULT_PROFILE_PATH)
    errors = validate_profile(
        profile,
        mode="frozen",
        require_integrity=True,
        raise_on_error=False,
    )
    assert any("status must be 'frozen'" in error for error in errors)
    assert any("source_revision" in error for error in errors)
    assert any("profile_sha256" in error for error in errors)


def test_non_loopback_endpoint_is_rejected_even_in_draft():
    profile = load_profile(DEFAULT_PROFILE_PATH)
    profile["llm"]["endpoint"]["base_url"] = "https://api.example.com/v1"
    errors = validate_profile(profile, mode="draft", raise_on_error=False)
    assert any("loopback-only" in error for error in errors)


def test_env_mapping_matches_existing_application_settings():
    profile = load_profile(DEFAULT_PROFILE_PATH)
    env = render_application_env(profile)
    assert env["CTA_LLM_PROVIDER"] == "openai_compatible_local"
    assert env["CTA_LLM_BASE_URL"] == "http://127.0.0.1:8093/v1"
    assert env["CTA_VISION_PROVIDER"] == "local_vlm"
    assert env["CTA_VISION_BASE_URL"] == "http://127.0.0.1:8091"
    assert env["CTA_ENABLE_LOCAL_OCR"] == "false"
    assert validate_application_env(profile, env) == []
    env["CTA_LLM_MODEL"] = "wrong-model"
    assert validate_application_env(profile, env)


def test_env_text_is_deterministic_and_parseable():
    profile = load_profile(DEFAULT_PROFILE_PATH)
    first = env_text(profile)
    second = env_text(profile)
    assert first == second
    parsed = parse_env_text(first)
    assert parsed == render_application_env(profile)


def test_seal_profile_creates_valid_integrity_binding():
    frozen = seal_profile(_fully_populated_profile(), sealed_at="2026-08-02T06:30:00Z")
    assert frozen["status"] == "frozen"
    assert frozen["integrity"]["profile_sha256"] == canonical_profile_sha256(frozen)
    assert validate_profile(frozen, mode="frozen", raise_on_error=False) == []


def test_tampered_frozen_profile_fails_integrity_check():
    frozen = seal_profile(_fully_populated_profile(), sealed_at="2026-08-02T06:30:00Z")
    frozen["application"]["request_timeout_seconds"] = 241
    errors = validate_profile(frozen, mode="frozen", raise_on_error=False)
    assert any("profile_sha256 mismatch" in error for error in errors)


def test_seal_rejects_missing_local_measurements():
    with pytest.raises(ProfileValidationError, match="cold_start_seconds"):
        seal_profile(load_profile(DEFAULT_PROFILE_PATH), sealed_at="2026-08-02T06:30:00Z")


def test_resolve_command_requires_explicit_runtime_python():
    command = ["${CTA_VLM_PYTHON}", "-m", "mlx_vlm.server"]
    assert resolve_command(command, {"CTA_VLM_PYTHON": "/tmp/venv/bin/python"})[0].endswith(
        "/python"
    )
    with pytest.raises(ProfileValidationError, match="CTA_VLM_PYTHON"):
        resolve_command(command, {})


class _HealthResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body


def test_component_status_requires_exact_loaded_model_identity(monkeypatch):
    from src.shared.model_profile.runtime import component_status

    profile = _fully_populated_profile()
    model = profile["vision"]["model"]["model_id"]

    monkeypatch.setattr(
        "src.shared.model_profile.runtime.fetch_served_models",
        lambda *a, **k: (model, "mlx-community/Some-Other-Model"),
    )
    monkeypatch.setattr(
        "src.shared.model_profile.runtime.fetch_loaded_model",
        lambda *a, **k: model,
    )
    status = component_status(profile, "vision")
    assert status.identity_match is True

    monkeypatch.setattr(
        "src.shared.model_profile.runtime.fetch_loaded_model",
        lambda *a, **k: "mlx-community/Some-Other-Model",
    )
    status = component_status(profile, "vision")
    assert status.identity_match is False
    assert "loaded" in status.detail
