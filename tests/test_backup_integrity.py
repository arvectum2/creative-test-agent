"""Tests for reusable backup integrity checking."""

import os
import sys
import tempfile
import zipfile

from scripts.backup_data import create_backup
from scripts.check_backup import check_backup


def test_check_backup_script_imports():
    from scripts.check_backup import check_backup

    assert callable(check_backup)


def test_check_backup_validates_generated_backup():
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_path = os.path.join(tmpdir, "test_check.zip")
        create_backup(backup_path)
        assert check_backup(backup_path) == []


def test_check_backup_fails_on_missing_file():
    errors = check_backup("/nonexistent/backup.zip")
    assert errors
    assert any("not found" in item.lower() for item in errors)


def test_check_backup_fails_on_bad_zip():
    import subprocess

    result = subprocess.run(
        [sys.executable, "scripts/check_backup.py", "/nonexistent/bad.zip"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__ + "/..")),
    )
    assert result.returncode != 0


def test_check_backup_detects_missing_manifest():
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_zip = os.path.join(tmpdir, "no_manifest.zip")
        with zipfile.ZipFile(bad_zip, "w") as archive:
            archive.writestr("some_file.txt", "data")
        errors = check_backup(bad_zip)
        assert errors
        assert any("manifest" in item.lower() for item in errors)


def test_backup_integrity_checker_script_exists():
    from pathlib import Path

    assert Path("scripts/check_backup.py").is_file()
