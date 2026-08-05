from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "cta_release_prep_001.py"
CLEAN_INSTALL_PATH = PROJECT_ROOT / "scripts" / "cta_release_prep_001_clean_install.py"
RUN_MIGRATIONS_PATH = PROJECT_ROOT / "scripts" / "run_migrations.py"


@pytest.fixture(autouse=True)
def _clear_settings_cache_after_each_test():
    """Keep env/settings mutations in this file from leaking across tests.

    ``get_settings`` is an ``lru_cache``; ``monkeypatch.setenv`` restores the
    process environment at teardown but does not invalidate the cached settings.
    Without clearing the cache here, a ``CTA_DATABASE_URL`` override set by one
    test would be observed by later health tests in the same pytest run.
    """
    yield
    from src.shared.config.settings import get_settings

    get_settings.cache_clear()


def _load_release_module():
    spec = importlib.util.spec_from_file_location("cta_release_prep_001", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_clean_install_module():
    spec = importlib.util.spec_from_file_location("cta_release_prep_001_clean_install", CLEAN_INSTALL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_run_migrations_module():
    spec = importlib.util.spec_from_file_location("cta_run_migrations", RUN_MIGRATIONS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_config_and_frozen_profile_contract() -> None:
    module = _load_release_module()
    config = module.load_config(PROJECT_ROOT, module.CONFIG)
    assert config["release_id"] == "CTA-RELEASE-PREP-001"
    assert config["app_version"] == module.app_version(PROJECT_ROOT)

    summary = module.model_summary(PROJECT_ROOT, config)
    assert summary["status"] == "frozen"
    assert summary["file_sha256"] == config["frozen_model_profile"]["expected_file_sha256"]
    assert summary["internal_profile_sha256"] == config["frozen_model_profile"]["expected_internal_profile_sha256"]
    assert summary["vision"]["weight_included"] is False
    assert summary["llm"]["weight_included"] is False


def test_onprem_environment_template_is_fail_closed() -> None:
    module = _load_release_module()
    config = module.load_config(PROJECT_ROOT, module.CONFIG)
    env_path = PROJECT_ROOT / config["environment_template"]
    module.validate_env(env_path.read_bytes(), config)


def test_release_bundle_is_deterministic_and_self_validating(tmp_path: Path) -> None:
    module = _load_release_module()
    revision = "0123456789abcdef0123456789abcdef01234567"

    first = module.build_release(
        PROJECT_ROOT,
        output_dir=tmp_path / "first",
        source_revision=revision,
    )
    second = module.build_release(
        PROJECT_ROOT,
        output_dir=tmp_path / "second",
        source_revision=revision,
    )

    first_zip = Path(first["zip_path"])
    second_zip = Path(second["zip_path"])
    assert first_zip.read_bytes() == second_zip.read_bytes()
    assert first["zip_sha256"] == second["zip_sha256"]

    validated = module.validate_release(
        first_zip,
        config_path=PROJECT_ROOT / module.CONFIG,
        project_root=PROJECT_ROOT,
    )
    assert validated["status"] == "PASS"
    assert validated["sbom_components"] > 0

    with zipfile.ZipFile(first_zip) as archive:
        names = archive.namelist()
        assert any(name.endswith("/release-manifest.json") for name in names)
        assert any(name.endswith("/sbom.cdx.json") for name in names)
        assert any(name.endswith("/dependency-export.txt") for name in names)
        assert any(name.endswith("/SHA256SUMS") for name in names)
        assert not any("/.git/" in name or "/.venv/" in name for name in names)
        assert not any(name.endswith((".gguf", ".safetensors", ".onnx", ".pt", ".pth", ".db")) for name in names)
        assert not any(name.endswith("/.env") or name.endswith("/.env.server") for name in names)


def test_validator_rejects_secret_and_checksum_drift(tmp_path: Path) -> None:
    module = _load_release_module()
    result = module.build_release(
        PROJECT_ROOT,
        output_dir=tmp_path / "release",
        source_revision="abcdef0123456789abcdef0123456789abcdef01",
    )
    bundle_dir = Path(result["bundle_dir"])
    target = bundle_dir / "README.md"
    target.write_text(target.read_text(encoding="utf-8") + "\nghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890\n", encoding="utf-8")

    with pytest.raises(module.ReleaseError):
        module.validate_release(
            bundle_dir,
            config_path=PROJECT_ROOT / module.CONFIG,
            project_root=PROJECT_ROOT,
        )


def test_validator_rejects_zip_traversal(tmp_path: Path) -> None:
    module = _load_release_module()
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("bundle/../escape.txt", "bad")
    with pytest.raises(module.ReleaseError, match="unsafe ZIP member"):
        module.validate_release(archive_path)


def test_clean_install_venv_creation_avoids_in_process_envbuilder(tmp_path: Path) -> None:
    module = _load_clean_install_module()
    source = CLEAN_INSTALL_PATH.read_text(encoding="utf-8")
    assert "venv.EnvBuilder" not in source
    assert "def _create_venv" in source

    venv_dir = tmp_path / ".venv"
    records: list[dict] = []
    python = module._create_venv(
        sys.executable,
        venv_dir,
        cwd=tmp_path,
        env=os.environ.copy(),
        records=records,
    )
    assert python.is_file()
    completed = subprocess.run([str(python), "-m", "pip", "--version"], capture_output=True, text=True)
    assert completed.returncode == 0
    assert "pip" in completed.stdout
    assert any(record.get("step") == "create-venv" for record in records)
    assert all(record.get("status") == "PASS" for record in records)


def test_clean_install_validation_env_isolates_closed_loop_base_url(tmp_path_factory) -> None:
    module = _load_clean_install_module()
    env = module._validation_env(tmp_path_factory.mktemp("w"))
    assert env["CTA_PORT"] == "18080"
    assert env["CTA_PUBLIC_BASE_URL"] == "http://127.0.0.1:18080"
    assert env.get("CTA_BASE_URL") == env["CTA_PUBLIC_BASE_URL"]
    assert "localhost:8000" not in env.get("CTA_BASE_URL", "")
    assert "127.0.0.1" in env.get("CTA_BASE_URL", "")


def test_run_migrations_creates_sqlite_parent_for_clean_install(monkeypatch, tmp_path: Path) -> None:
    db_file = tmp_path / "data" / "db" / "creative_test_agent.db"
    monkeypatch.setenv("CTA_DATABASE_URL", f"sqlite:///{db_file}")
    from src.shared.config.settings import get_settings

    get_settings.cache_clear()
    module = _load_run_migrations_module()
    module._ensure_sqlite_parent()
    assert db_file.parent.is_dir()


def test_run_migrations_skips_non_sqlite_url(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CTA_DATABASE_URL", "postgresql://host/db")
    from src.shared.config.settings import get_settings

    get_settings.cache_clear()
    module = _load_run_migrations_module()
    module._ensure_sqlite_parent()
    assert not (tmp_path / "data").exists()


def test_onprem_template_admin_name_is_source_safe() -> None:
    env_text = (PROJECT_ROOT / ".env.onprem.example").read_text(encoding="utf-8")
    line = next(line for line in env_text.splitlines() if line.startswith("CTA_BOOTSTRAP_ADMIN_NAME="))
    assert '"On-Prem Admin"' in line


def _read_env_template() -> dict[str, str]:
    env_text = (PROJECT_ROOT / ".env.onprem.example").read_text(encoding="utf-8")
    return {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in env_text.splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
    }


def test_onprem_template_matches_frozen_contract_runtime() -> None:
    import json as _json

    env = _read_env_template()
    contract_path = (
        PROJECT_ROOT
        / "config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json"
    )
    contract = _json.loads(contract_path.read_text(encoding="utf-8"))

    app = contract["application"]
    assert env.get("CTA_VISION_API_STYLE") == app["vision_api_style"] == "openai_compatible"
    assert env["CTA_LLM_PROVIDER"] == app["llm_provider"] == "openai_compatible_local"
    assert env["CTA_VISION_PROVIDER"] == app["vision_provider"] == "local_vlm"
    assert env["CTA_ALLOW_CLOUD_LLM"] == str(app["allow_cloud_llm"]).lower() == "false"
    assert env["CTA_LOCAL_ONLY_MODE"] == str(app["local_only_mode"]).lower() == "true"

    timeout = int(env["CTA_LLM_TIMEOUT_SECONDS"])
    assert timeout >= int(app["request_timeout_seconds"])
    assert int(env["CTA_VISION_TIMEOUT_SECONDS"]) >= int(app["request_timeout_seconds"])

    # vision endpoint contract
    assert env["CTA_VISION_BASE_URL"] == contract["vision"]["endpoint"]["base_url"]
    assert env["CTA_LLM_BASE_URL"] == contract["llm"]["endpoint"]["base_url"]
    assert env["CTA_VISION_MODEL"] == contract["vision"]["model"]["model_id"]
    assert env["CTA_LLM_MODEL"] == contract["llm"]["model"]["model_id"]


def test_onprem_runbook_model_cli_uses_frozen_profile_flag_order() -> None:
    runbook_text = (
        PROJECT_ROOT / "docs/releases/CTA-RELEASE-PREP-001_ONPREM_RUNBOOK_RU.md"
    ).read_text(encoding="utf-8")
    found = 0
    for line in runbook_text.splitlines():
        if "cta_model_001.py" not in line:
            continue
        cleaned = line.strip()
        if not cleaned.startswith("python scripts/cta_model_001.py"):
            continue
        # flag must come AFTER the subcommand selector, not before it
        assert cleaned.index("--profile") > cleaned.index("cta_model_001.py"), cleaned
        found += 1
    assert found >= 3


def test_settings_accepts_onprem_security_env_fields(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CTA_SECURITY_FAIL_CLOSED=true\n"
        "CTA_SECURITY_HEADERS_ENABLED=true\n"
        "CTA_SECRET_KEY=change-me\n",
        encoding="utf-8",
    )
    from src.shared.config.settings import Settings

    settings = Settings(_env_file=str(env_file))
    assert settings.security_fail_closed is True
    assert settings.security_headers_enabled is True


def test_migrations_are_in_sync_with_orm_models(tmp_path: Path) -> None:
    db_file = tmp_path / "schema-sync.db"
    env = {**os.environ, "CTA_DATABASE_URL": f"sqlite:///{db_file}"}
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    drift = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert drift.returncode == 0, drift.stdout + drift.stderr
