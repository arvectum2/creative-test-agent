#!/usr/bin/env python3
"""Restore Creative Test Agent data from a validated local backup.

Usage:
    python scripts/restore_data.py <backup.zip> [--force] [--skip-pre-restore-backup]

The default path is fail-safe: validation and a pre-restore backup must succeed
before any current workspace file is replaced.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.backup_common import (
    DATABASE_ARCNAME,
    load_backup_manifest,
    safe_extract_backup,
    validate_backup,
    verify_restored_payload,
)


def _detect_app_running(port: int = 8000) -> bool:
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("GET", "/health")
        response = connection.getresponse()
        connection.close()
        return response.status == 200
    except Exception:
        return False


def _sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    raw = database_url.removeprefix("sqlite:///")
    if not raw or raw == ":memory:":
        return None
    return Path(raw).expanduser().resolve()


def _replace_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(f".{target.name}.restore-{uuid.uuid4().hex}")
    try:
        shutil.copy2(source, staged)
        os.replace(staged, target)
    finally:
        staged.unlink(missing_ok=True)


def _replace_directory(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.parent / f".{target.name}.restore-{uuid.uuid4().hex}"
    previous = target.parent / f".{target.name}.previous-{uuid.uuid4().hex}"
    shutil.copytree(source, staged)
    moved_previous = False
    try:
        if target.exists():
            os.replace(target, previous)
            moved_previous = True
        os.replace(staged, target)
        if moved_previous:
            shutil.rmtree(previous, ignore_errors=True)
    except Exception:
        if target.exists() and not moved_previous:
            shutil.rmtree(target, ignore_errors=True)
        if moved_previous and previous.exists() and not target.exists():
            os.replace(previous, target)
        raise
    finally:
        shutil.rmtree(staged, ignore_errors=True)
        if previous.exists() and target.exists():
            shutil.rmtree(previous, ignore_errors=True)


def restore_backup(
    backup_path: str,
    force: bool = False,
    *,
    create_pre_restore_backup: bool = True,
) -> dict:
    from src.shared.config.settings import get_settings
    from src.shared.db.session import close_db

    settings = get_settings()
    source_archive = Path(backup_path).expanduser().resolve()
    errors = validate_backup(source_archive)
    if errors:
        raise RuntimeError("Backup validation failed: " + "; ".join(errors))
    if not force and _detect_app_running(settings.port):
        raise RuntimeError(
            f"App appears to be running on 127.0.0.1:{settings.port}; stop it first or use --force"
        )

    database_path = _sqlite_path(settings.database_url)
    if database_path is None:
        raise RuntimeError("Restore currently supports a persistent SQLite database only")
    storage_root = Path(settings.storage_root).expanduser().resolve()
    exports_root = Path(settings.exports_root).expanduser().resolve()
    backup_root = Path(settings.backup_root).expanduser().resolve()
    backup_root.mkdir(parents=True, exist_ok=True)

    manifest = load_backup_manifest(source_archive)
    close_db()
    pre_restore_path: str | None = None
    if create_pre_restore_backup:
        from scripts.backup_data import create_backup

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        pre_restore = backup_root / f"pre_restore_{timestamp}_{source_archive.name}"
        try:
            pre_restore_path = create_backup(str(pre_restore))
        except Exception as exc:
            raise RuntimeError(f"Pre-restore backup failed; restore aborted: {exc}") from exc

    restored = {"database": False, "storage": False, "exports": False}
    with tempfile.TemporaryDirectory(prefix="cta-restore-") as tmpdir_value:
        extracted = Path(tmpdir_value)
        safe_extract_backup(source_archive, extracted)
        included = manifest.get("included", {})
        if included.get("database"):
            _replace_file(extracted / DATABASE_ARCNAME, database_path)
            restored["database"] = True
        if included.get("storage"):
            _replace_directory(extracted / "storage", storage_root)
            restored["storage"] = True
        if included.get("exports"):
            _replace_directory(extracted / "exports", exports_root)
            restored["exports"] = True

    verification_errors = verify_restored_payload(
        manifest,
        database_path=database_path,
        storage_root=storage_root,
        exports_root=exports_root,
    )
    if verification_errors:
        raise RuntimeError("Restored workspace failed verification: " + "; ".join(verification_errors))

    result = {
        "status": "completed",
        "restored_at": datetime.now(timezone.utc).isoformat(),
        "backup_path": str(source_archive),
        "backup_id": manifest.get("backup_id"),
        "format_version": manifest.get("format_version"),
        "pre_restore_backup_path": pre_restore_path,
        "restored": restored,
        "verified": True,
        "verification_errors": [],
        "same_configured_paths_required": True,
    }
    print(f"Restored backup: {source_archive.name}")
    print(f"  Database: {'restored' if restored['database'] else 'not included'}")
    print(f"  Storage: {'restored' if restored['storage'] else 'not included'}")
    print(f"  Exports: {'restored' if restored['exports'] else 'not included'}")
    print(f"  Pre-restore backup: {pre_restore_path or 'explicitly skipped'}")
    print("  Integrity verification: PASS")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore a verified Creative Test Agent backup")
    parser.add_argument("backup", help="Path to the backup ZIP")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Proceed even when the local health endpoint appears to be running",
    )
    parser.add_argument(
        "--skip-pre-restore-backup",
        action="store_true",
        help="Emergency-only: restore without first backing up the current workspace",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = restore_backup(
            args.backup,
            args.force,
            create_pre_restore_backup=not args.skip_pre_restore_backup,
        )
    except Exception as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
