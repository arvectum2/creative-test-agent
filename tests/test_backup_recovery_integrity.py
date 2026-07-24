from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

from scripts.backup_common import BACKUP_FORMAT_VERSION, validate_backup

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _environment(tmp_path: Path) -> tuple[dict[str, str], Path, Path, Path, Path]:
    database = tmp_path / "workspace.db"
    storage = tmp_path / "storage"
    exports = tmp_path / "exports"
    backups = tmp_path / "backups"
    storage.mkdir()
    exports.mkdir()
    backups.mkdir()
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE rehearsal_value (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO rehearsal_value (id, value) VALUES (1, 'baseline')")
        connection.commit()
    finally:
        connection.close()
    (storage / "input.txt").write_text("immutable input\n", encoding="utf-8")
    (exports / "report.txt").write_text("local report\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "CTA_DATABASE_URL": f"sqlite:///{database}",
            "CTA_STORAGE_ROOT": str(storage),
            "CTA_EXPORTS_ROOT": str(exports),
            "CTA_BACKUP_ROOT": str(backups),
            "CTA_BACKUP_INCLUDE_UPLOADS": "true",
            "CTA_BACKUP_INCLUDE_EXPORTS": "true",
            "CTA_LOCAL_ONLY_MODE": "true",
            "CTA_ALLOW_CLOUD_LLM": "false",
            "CTA_ENABLE_AUTH": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env, database, storage, exports, backups


def _run(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPOSITORY_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )


def test_backup_v2_detects_tampering_and_restores_exact_payload(tmp_path: Path):
    env, database, storage, exports, backups = _environment(tmp_path)
    archive = backups / "primary.zip"

    created = _run("scripts/backup_data.py", str(archive), env=env)
    assert created.returncode == 0, created.stdout
    assert validate_backup(archive) == []

    with zipfile.ZipFile(archive, "r") as source:
        manifest = json.loads(source.read("manifest.json"))
        assert manifest["format_version"] == BACKUP_FORMAT_VERSION
        assert manifest["included"] == {"database": True, "storage": True, "exports": True}
        assert manifest["table_counts"]["rehearsal_value"] == 1
        assert {item["path"] for item in manifest["files"]} == {
            "creative_test_agent.db",
            "storage/input.txt",
            "exports/report.txt",
        }

        tampered = backups / "tampered.zip"
        with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename == "storage/input.txt":
                    payload = b"tampered\n"
                target.writestr(info.filename, payload)
    assert any("SHA-256 mismatch for storage/input.txt" in item for item in validate_backup(tampered))

    connection = sqlite3.connect(database)
    try:
        connection.execute("UPDATE rehearsal_value SET value='damaged' WHERE id=1")
        connection.commit()
    finally:
        connection.close()
    (storage / "input.txt").unlink()
    (exports / "report.txt").write_text("damaged\n", encoding="utf-8")

    restored = _run("scripts/restore_data.py", str(archive), "--force", env=env)
    assert restored.returncode == 0, restored.stdout
    connection = sqlite3.connect(database)
    try:
        value = connection.execute("SELECT value FROM rehearsal_value WHERE id=1").fetchone()[0]
    finally:
        connection.close()
    assert value == "baseline"
    assert (storage / "input.txt").read_text(encoding="utf-8") == "immutable input\n"
    assert (exports / "report.txt").read_text(encoding="utf-8") == "local report\n"

    pre_restore = list(backups.glob("pre_restore_*_primary.zip"))
    assert len(pre_restore) == 1
    assert validate_backup(pre_restore[0]) == []


def test_backup_validator_rejects_traversal_and_unrecorded_payload(tmp_path: Path):
    archive = tmp_path / "unsafe.zip"
    manifest = {
        "format_version": BACKUP_FORMAT_VERSION,
        "backup_id": "unsafe",
        "created_at": "2026-01-01T00:00:00+00:00",
        "app": "creative-test-agent",
        "included": {"database": False, "storage": False, "exports": False},
        "files": [],
        "table_counts": {},
    }
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as target:
        target.writestr("manifest.json", json.dumps(manifest))
        target.writestr("../escape.txt", b"escape")
    errors = validate_backup(archive)
    assert any("unsafe archive member" in item for item in errors)
    assert any("unrecorded archive members" in item for item in errors)
