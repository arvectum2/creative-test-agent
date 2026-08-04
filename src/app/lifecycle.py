"""Application startup lifecycle and process-local infrastructure setup."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

from src.shared.config.settings import Settings
from src.shared.db.session import init_db
from src.shared.security.config import security_fail_closed
from src.shared.security.hardening import validate_security_posture

_LOG_FORMATS = {
    "plain": "%(asctime)s [%(levelname)s] %(message)s",
    "verbose": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
}


def configure_logging(settings: Settings) -> None:
    """Configure process logging once, before database initialization."""

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if settings.log_file:
        log_path = Path(settings.log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format=_LOG_FORMATS.get(settings.log_format, _LOG_FORMATS["verbose"]),
        handlers=handlers,
    )


def prepare_local_directories(settings: Settings) -> None:
    """Create all writable local directories required by the configured runtime."""

    for raw_path in (
        settings.storage_root,
        settings.exports_root,
        settings.backup_root,
    ):
        Path(raw_path).expanduser().mkdir(parents=True, exist_ok=True)

    sqlite_prefix = "sqlite:///"
    if settings.database_url.startswith(sqlite_prefix):
        database_path = Path(settings.database_url.removeprefix(sqlite_prefix)).expanduser()
        if database_path.parent != Path(""):
            database_path.parent.mkdir(parents=True, exist_ok=True)


def validate_startup_security(settings: Settings) -> None:
    """Fail closed before opening the database when blocking controls are violated."""

    posture = validate_security_posture(settings)
    if not security_fail_closed() or not posture.blocking_errors:
        return
    details = "; ".join(
        f"{item.key}: {item.message}" for item in posture.blocking_errors
    )
    raise RuntimeError(f"Security posture blocked startup: {details}")


@asynccontextmanager
async def application_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize local infrastructure using FastAPI's supported lifespan API."""

    settings: Settings = app.state.settings
    configure_logging(settings)
    prepare_local_directories(settings)
    validate_startup_security(settings)
    init_db()
    yield
