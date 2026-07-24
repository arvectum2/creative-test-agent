#!/usr/bin/env python3
"""Create a verified local backup of Creative Test Agent data.

Usage:
    python scripts/backup_data.py [output_path]

The v2 archive contains a consistent SQLite snapshot, optional storage and
exports payloads, and a manifest that records size and SHA-256 for every file.
Secrets, environment files, logs and session cookies are never added.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.backup_common import (
    BACKUP_FORMAT_VERSION,
    DATABASE_ARCNAME,
    MANIFEST_NAME,
    build_file_record,
    sqlite_integrity_ok,
    sqlite_table_counts,
    validate_backup,
)


def get_entity_counts() -> dict[str, int]:
    """Return the stable legacy operational entity summary.

    The function remains public for scripts and monitoring introduced before
    backup format v2. The v2 manifest additionally records every SQLite table,
    but these semantic keys are kept for backward compatibility.
    """

    counts = {
        "clients": 0,
        "projects": 0,
        "creative_assets": 0,
        "test_runs": 0,
        "reports": 0,
        "brandbooks": 0,
        "knowledge_items": 0,
        "export_jobs": 0,
    }
    model_paths = {
        "clients": "src.modules.clients.models.Client",
        "projects": "src.modules.projects.models.Project",
        "creative_assets": "src.modules.creative_assets.models.CreativeAsset",
        "test_runs": "src.modules.test_runs.models.TestRun",
        "reports": "src.modules.report_generator.models.Report",
        "brandbooks": "src.modules.brandbooks.models.BrandbookDocument",
        "knowledge_items": "src.modules.knowledge_base.models.KnowledgeItem",
        "export_jobs": "src.modules.export_jobs.models.ExportJob",
    }
    try:
        from src.shared.db.repository import db_session

        with db_session() as db:
            for key, model_path in model_paths.items():
                module_name, class_name = model_path.rsplit(".", 1)
                module = __import__(module_name, fromlist=[class_name])
                counts[key] = int(db.query(getattr(module, class_name)).count())
    except Exception:
        # Backup creation itself uses snapshot-level table counts and does not
        # depend on this compatibility summary being available.
        return counts
    return counts


def _write_audit_log(event_type: str, detail: str, payload: dict | None = None) -> None:
    try:
        from src.shared.db.session import check_db_connection

        if check_db_connection():
            from src.modules.audit_log.service import write_audit_event

            write_audit_event(
                event_type,
                "backup",
                "system",
                {"detail": detail, **(payload or {})},
            )
    except Exception:
        # Backup must not become unavailable because audit storage is degraded.
        pass


def _sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    raw = database_url.removeprefix("sqlite:///")
    if not raw or raw == ":memory:":
        return None
    return Path(raw).expanduser().resolve()


def _snapshot_sqlite(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
    destination_connection = sqlite3.connect(str(destination), timeout=30)
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()
    if not sqlite_integrity_ok(destination):
        raise RuntimeError("SQLite snapshot failed PRAGMA integrity_check")


def _copy_payload(source: Path, destination: Path) -> bool:
    if not source.is_dir():
        return False
    files = [path for path in source.rglob("*") if path.is_file() and not path.is_symlink()]
    if not files:
        return False
    for path in files:
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return True


def _payload_records(root: Path) -> list[dict]:
    records: list[dict] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        archive_path = path.relative_to(root).as_posix()
        if any(part.lower() == ".env" or part.lower().startswith(".env.") for part in path.parts):
            raise RuntimeError(f"Refusing to include environment file: {path}")
        records.append(build_file_record(path, archive_path))
    return records


def create_backup(output_path: str | None = None) -> str:
    from src.shared.config.settings import get_settings

    settings = get_settings()
    backup_root = Path(settings.backup_root).expanduser().resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    if output_path:
        backup_path = Path(output_path).expanduser().resolve()
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        backup_path = backup_root / f"cta_backup_{timestamp}.zip"
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    database_path = _sqlite_path(settings.database_url)
    if database_path is None:
        raise RuntimeError("Backup currently supports a persistent SQLite database only")

    storage_root = Path(settings.storage_root).expanduser().resolve()
    exports_root = Path(settings.exports_root).expanduser().resolve()
    for protected_root in (storage_root, exports_root):
        try:
            backup_path.relative_to(protected_root)
        except ValueError:
            continue
        raise RuntimeError("Backup output must not be placed inside storage or exports")

    with tempfile.TemporaryDirectory(prefix="cta-backup-") as tmpdir_value:
        tmpdir = Path(tmpdir_value)
        snapshot_path = tmpdir / DATABASE_ARCNAME
        _snapshot_sqlite(database_path, snapshot_path)

        include_storage = False
        include_exports = False
        if settings.backup_include_uploads:
            include_storage = _copy_payload(storage_root, tmpdir / "storage")
        if settings.backup_include_exports:
            include_exports = _copy_payload(exports_root, tmpdir / "exports")

        files = _payload_records(tmpdir)
        table_counts = sqlite_table_counts(snapshot_path)
        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "backup_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "app": "creative-test-agent",
            "database_url_type": "sqlite",
            "included": {
                "database": True,
                "storage": include_storage,
                "exports": include_exports,
            },
            "files": files,
            "file_count": len(files),
            "payload_size_bytes": sum(item["size_bytes"] for item in files),
            "table_counts": table_counts,
            # Stable field retained for older operational tooling.
            "counts": get_entity_counts(),
            "safety": {
                "contains_environment_files": False,
                "contains_secrets_by_design": False,
                "sqlite_snapshot_method": "sqlite_backup_api",
                "all_payload_files_hashed": True,
            },
        }
        manifest_path = tmpdir / MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        temporary_archive = backup_path.with_name(f".{backup_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(temporary_archive, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                archive.write(manifest_path, MANIFEST_NAME)
                for item in files:
                    archive.write(tmpdir / item["path"], item["path"])
            errors = validate_backup(temporary_archive)
            if errors:
                raise RuntimeError("Created backup failed validation: " + "; ".join(errors))
            os.replace(temporary_archive, backup_path)
        finally:
            temporary_archive.unlink(missing_ok=True)

    _write_audit_log(
        "backup_created",
        str(backup_path),
        {
            "format_version": BACKUP_FORMAT_VERSION,
            "backup_sha256_recorded_per_file": True,
            "table_count": len(table_counts),
        },
    )
    print(f"Backup created: {backup_path}")
    print("  Database: consistent SQLite snapshot included")
    print(f"  Storage:  {'included' if include_storage else 'skipped or empty'}")
    print(f"  Exports:  {'included' if include_exports else 'skipped or empty'}")
    print(f"  Payload files: {len(files)}")
    print(f"  Database tables: {len(table_counts)}")
    return str(backup_path)


def main() -> int:
    output_path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        create_backup(output_path)
    except Exception as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
