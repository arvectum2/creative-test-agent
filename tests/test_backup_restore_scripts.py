"""Tests for backup and restore scripts."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def test_backup_script_imports():
    from scripts.backup_data import create_backup, get_entity_counts

    assert callable(create_backup)
    assert callable(get_entity_counts)


def test_restore_script_imports():
    from scripts.restore_data import restore_backup

    assert callable(restore_backup)


def test_get_entity_counts():
    from scripts.backup_data import get_entity_counts

    counts = get_entity_counts()
    assert isinstance(counts, dict)
    assert "clients" in counts
    assert "projects" in counts
    assert "test_runs" in counts


def test_backup_creates_zip():
    from scripts.backup_data import create_backup

    with tempfile.TemporaryDirectory() as tmpdir:
        backup_path = os.path.join(tmpdir, "test_backup.zip")
        result = create_backup(backup_path)
        assert os.path.isfile(result)
        assert result == backup_path
        assert zipfile.is_zipfile(result)


def test_backup_zip_contains_manifest():
    from scripts.backup_data import create_backup

    with tempfile.TemporaryDirectory() as tmpdir:
        backup_path = os.path.join(tmpdir, "test_manifest.zip")
        create_backup(backup_path)
        with zipfile.ZipFile(backup_path, "r") as archive:
            names = archive.namelist()
            assert "manifest.json" in names
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["app"] == "creative-test-agent"
            assert "created_at" in manifest
            assert "counts" in manifest
            assert "table_counts" in manifest
            assert "database_url_type" in manifest


def test_backup_excludes_env():
    from scripts.backup_data import create_backup

    with tempfile.TemporaryDirectory() as tmpdir:
        backup_path = os.path.join(tmpdir, "test_noenv.zip")
        create_backup(backup_path)
        with zipfile.ZipFile(backup_path, "r") as archive:
            names = archive.namelist()
            env_files = [name for name in names if ".env" in name and not name.startswith("__")]
            assert len(env_files) == 0, f"Found .env files: {env_files}"


def test_backup_has_no_path_traversal():
    from scripts.backup_data import create_backup

    with tempfile.TemporaryDirectory() as tmpdir:
        backup_path = os.path.join(tmpdir, "test_safe.zip")
        create_backup(backup_path)
        with zipfile.ZipFile(backup_path, "r") as archive:
            names = archive.namelist()
            traversal = [name for name in names if ".." in name or name.startswith("/")]
            assert len(traversal) == 0, f"Path traversal: {traversal}"


def _isolated_environment(root: Path) -> tuple[dict[str, str], Path]:
    database = root / "isolated.db"
    storage = root / "storage"
    exports = root / "exports"
    backups = root / "backups"
    storage.mkdir()
    exports.mkdir()
    backups.mkdir()
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE smoke (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO smoke (value) VALUES ('baseline')")
        connection.commit()
    finally:
        connection.close()
    (storage / "source.txt").write_text("source\n", encoding="utf-8")
    (exports / "report.txt").write_text("report\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "CTA_DATABASE_URL": f"sqlite:///{database}",
            "CTA_STORAGE_ROOT": str(storage),
            "CTA_EXPORTS_ROOT": str(exports),
            "CTA_BACKUP_ROOT": str(backups),
            "CTA_LOCAL_ONLY_MODE": "true",
            "CTA_ALLOW_CLOUD_LLM": "false",
            "CTA_ENABLE_AUTH": "false",
        }
    )
    return env, database


def test_restore_script_validates_backup_structure():
    repository_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmpdir_value:
        root = Path(tmpdir_value)
        env, database = _isolated_environment(root)
        backup_path = root / "test_restore.zip"
        created = subprocess.run(
            [sys.executable, "scripts/backup_data.py", str(backup_path)],
            capture_output=True,
            text=True,
            cwd=repository_root,
            env=env,
            timeout=120,
        )
        assert created.returncode == 0, created.stdout + created.stderr

        connection = sqlite3.connect(database)
        try:
            connection.execute("UPDATE smoke SET value='damaged'")
            connection.commit()
        finally:
            connection.close()

        restored = subprocess.run(
            [sys.executable, "scripts/restore_data.py", str(backup_path), "--force"],
            capture_output=True,
            text=True,
            cwd=repository_root,
            env=env,
            timeout=120,
        )
        assert restored.returncode == 0, restored.stdout + restored.stderr
        connection = sqlite3.connect(database)
        try:
            assert connection.execute("SELECT value FROM smoke").fetchone()[0] == "baseline"
        finally:
            connection.close()


def test_restore_script_rejects_missing_manifest():
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_zip = os.path.join(tmpdir, "bad.zip")
        with zipfile.ZipFile(bad_zip, "w") as archive:
            archive.writestr("some_file.txt", "data")

        result = subprocess.run(
            [sys.executable, "scripts/restore_data.py", bad_zip, "--force"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert result.returncode != 0
        assert "manifest" in result.stderr.lower()
