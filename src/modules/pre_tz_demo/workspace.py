"""Workspace and isolated runtime management for the PRE-TZ demo."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True, slots=True)
class DemoPaths:
    workspace: Path
    fixture: Path
    database: Path
    storage: Path
    exports: Path
    backups: Path
    manifest: Path


def prepare_demo_paths(
    workspace: str | Path,
    *,
    fixture_path: str | Path | None,
    reset: bool,
    respondent_count: int,
) -> DemoPaths:
    workspace_path = Path(workspace).expanduser().resolve()
    if reset:
        _reset_workspace(workspace_path)
    else:
        workspace_path.mkdir(parents=True, exist_ok=True)

    fixture = _resolve_fixture(fixture_path)
    if respondent_count < 1 or respondent_count > 500:
        raise ValueError("respondent_count must be between 1 and 500")

    paths = DemoPaths(
        workspace=workspace_path,
        fixture=fixture,
        database=workspace_path / "creative_test_agent_demo.db",
        storage=workspace_path / "storage",
        exports=workspace_path / "exports",
        backups=workspace_path / "backups",
        manifest=workspace_path / "demo_manifest.json",
    )
    for directory in (paths.storage, paths.exports, paths.backups):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def _resolve_fixture(fixture_path: str | Path | None) -> Path:
    fixture = (
        Path(fixture_path).expanduser().resolve()
        if fixture_path
        else Path(__file__).resolve().parents[3]
        / "examples"
        / "pre_tz"
        / "messy_campaign_export.csv"
    )
    if not fixture.is_file():
        raise FileNotFoundError(f"Demo fixture not found: {fixture}")
    return fixture


def _reset_workspace(workspace: Path) -> None:
    import shutil

    resolved = workspace.expanduser().resolve()
    forbidden = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}
    if resolved in forbidden or len(resolved.parts) < 3:
        raise ValueError(f"Refusing to reset unsafe demo workspace: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


@contextmanager
def isolated_demo_environment(paths: DemoPaths) -> Iterator[None]:
    """Temporarily bind the process-wide settings and DB to the demo workspace."""

    from src.shared.config.settings import get_settings
    from src.shared.db.session import close_db, init_db

    settings = get_settings()
    original_settings = {
        "database_url": settings.database_url,
        "storage_root": settings.storage_root,
        "exports_root": settings.exports_root,
        "backup_root": settings.backup_root,
        "local_only_mode": settings.local_only_mode,
        "allow_cloud_llm": settings.allow_cloud_llm,
        "enable_auth": settings.enable_auth,
        "host": settings.host,
        "public_base_url": settings.public_base_url,
        "trusted_hosts": settings.trusted_hosts,
        "cors_allowed_origins": settings.cors_allowed_origins,
    }

    settings.database_url = f"sqlite:///{paths.database}"
    settings.storage_root = str(paths.storage)
    settings.exports_root = str(paths.exports)
    settings.backup_root = str(paths.backups)
    settings.local_only_mode = True
    settings.allow_cloud_llm = False
    settings.enable_auth = False
    settings.host = "127.0.0.1"
    settings.public_base_url = "http://localhost:8000"
    settings.trusted_hosts = "localhost,127.0.0.1,test,testserver"
    settings.cors_allowed_origins = ""

    close_db()
    try:
        init_db()
        yield
    finally:
        close_db()
        for key, value in original_settings.items():
            setattr(settings, key, value)
