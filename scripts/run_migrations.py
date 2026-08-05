#!/usr/bin/env python3
"""
Run Alembic migrations to upgrade to the latest revision.

Usage:
    python scripts/run_migrations.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _ensure_sqlite_parent() -> None:
    """Create the SQLite parent directory for a clean-machine install.

    A fresh on-prem deployment has no ``data/`` tree (it is not shipped in the
    release bundle), while the runbook runs migrations before the application
    starts. Without this step ``sqlite3`` fails with "unable to open database
    file" on a clean machine.
    """
    from src.shared.config.settings import get_settings

    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        return
    raw = url[len("sqlite:///") :]
    if not raw or raw == ":memory:":
        return
    Path(raw).expanduser().parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    from alembic.config import Config
    from alembic import command

    print("Running migrations...")

    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))

    try:
        _ensure_sqlite_parent()
        command.upgrade(alembic_cfg, "head")
        print("Migrations completed successfully.")
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
