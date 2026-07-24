#!/usr/bin/env python3
"""Validate a Creative Test Agent backup archive.

Usage:
    python scripts/check_backup.py data/backups/cta_backup_YYYYMMDD_HHMMSS.zip
"""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.backup_common import load_backup_manifest, validate_backup


def check_backup(backup_path: str) -> list[str]:
    """Return validation errors without terminating the caller process."""
    return validate_backup(backup_path)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/check_backup.py <backup.zip>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    print(f"Checking backup: {path}")
    errors = check_backup(str(path))
    if errors:
        print(f"Backup integrity: FAIL ({len(errors)} issue(s))")
        for error in errors:
            print(f"  - {error}")
        return 1
    manifest = load_backup_manifest(path)
    included = manifest.get("included", {})
    print("Backup integrity: PASS")
    print(f"  Format version: {manifest.get('format_version')}")
    print(f"  Backup ID: {manifest.get('backup_id')}")
    print(f"  Payload files: {manifest.get('file_count', len(manifest.get('files', [])))}")
    print(f"  Database: {'included' if included.get('database') else 'not included'}")
    print(f"  Storage: {'included' if included.get('storage') else 'not included'}")
    print(f"  Exports: {'included' if included.get('exports') else 'not included'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
