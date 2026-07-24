#!/usr/bin/env python3
"""Shared backup-format, integrity and safe-extraction helpers.

The v2 backup format records every archived payload file with byte size and
SHA-256. ``manifest.json`` is intentionally not self-hashed; all other archive
members must be declared exactly once in the manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

BACKUP_FORMAT_VERSION = 2
MANIFEST_NAME = "manifest.json"
DATABASE_ARCNAME = "creative_test_agent.db"
_ALLOWED_ROOTS = {"storage", "exports"}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sqlite_integrity_ok(path: str | Path) -> bool:
    import sqlite3

    try:
        connection = sqlite3.connect(str(Path(path)))
        try:
            row = connection.execute("PRAGMA integrity_check").fetchone()
            return bool(row and str(row[0]).lower() == "ok")
        finally:
            connection.close()
    except Exception:
        return False


def sqlite_table_counts(path: str | Path) -> dict[str, int]:
    import sqlite3

    database = Path(path)
    if not database.is_file():
        return {}
    connection = sqlite3.connect(str(database))
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        counts: dict[str, int] = {}
        for name in names:
            escaped = name.replace('"', '""')
            counts[name] = int(connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0])
        return counts
    finally:
        connection.close()


def build_file_record(path: str | Path, archive_path: str) -> dict[str, Any]:
    source = Path(path)
    return {
        "path": archive_path,
        "size_bytes": source.stat().st_size,
        "sha256": sha256_file(source),
    }


def load_backup_manifest(backup_path: str | Path) -> dict[str, Any]:
    with zipfile.ZipFile(Path(backup_path), "r") as archive:
        if MANIFEST_NAME not in archive.namelist():
            raise ValueError("backup is missing manifest.json")
        try:
            manifest = json.loads(archive.read(MANIFEST_NAME))
        except json.JSONDecodeError as exc:
            raise ValueError("manifest.json is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must contain an object")
    return manifest


def _unsafe_member_reason(name: str) -> str | None:
    if not name or "\\" in name:
        return "empty name or backslash separator"
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return "absolute or traversal path"
    if ":" in path.parts[0]:
        return "drive-like path"
    if any(part.lower() == ".env" or part.lower().startswith(".env.") for part in path.parts):
        return "environment file"
    return None


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def validate_backup(backup_path: str | Path) -> list[str]:
    path = Path(backup_path)
    errors: list[str] = []
    if not path.is_file():
        return [f"backup file not found: {path}"]
    try:
        archive = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile:
        return ["backup is not a readable ZIP archive"]

    with archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            errors.append("duplicate archive members: " + ", ".join(duplicates))
        for info in infos:
            reason = _unsafe_member_reason(info.filename)
            if reason:
                errors.append(f"unsafe archive member {info.filename!r}: {reason}")
            if _is_zip_symlink(info):
                errors.append(f"symbolic links are not allowed: {info.filename}")
            if info.flag_bits & 0x1:
                errors.append(f"encrypted archive member is not allowed: {info.filename}")

        if MANIFEST_NAME not in names:
            errors.append("manifest.json is missing")
            return errors
        try:
            manifest = json.loads(archive.read(MANIFEST_NAME))
        except Exception as exc:
            errors.append(f"manifest.json is invalid: {exc}")
            return errors
        if not isinstance(manifest, dict):
            errors.append("manifest.json must contain an object")
            return errors
        if manifest.get("app") != "creative-test-agent":
            errors.append("manifest app must be creative-test-agent")
        if not manifest.get("created_at"):
            errors.append("manifest created_at is required")
        version = manifest.get("format_version", 1)
        if version != BACKUP_FORMAT_VERSION:
            errors.append(
                f"unsupported backup format_version {version!r}; expected {BACKUP_FORMAT_VERSION}"
            )
        included = manifest.get("included")
        if not isinstance(included, dict):
            errors.append("manifest included must be an object")
            included = {}
        for key in ("database", "storage", "exports"):
            if not isinstance(included.get(key), bool):
                errors.append(f"manifest included.{key} must be boolean")

        files = manifest.get("files")
        if not isinstance(files, list):
            errors.append("manifest files must be a list")
            files = []
        records: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(files):
            if not isinstance(item, dict):
                errors.append(f"manifest files[{index}] must be an object")
                continue
            member = item.get("path")
            if not isinstance(member, str) or not member:
                errors.append(f"manifest files[{index}].path is required")
                continue
            if member in records:
                errors.append(f"manifest contains duplicate file record: {member}")
                continue
            records[member] = item
            reason = _unsafe_member_reason(member)
            if reason:
                errors.append(f"unsafe manifest path {member!r}: {reason}")
            size = item.get("size_bytes")
            digest = item.get("sha256")
            if not isinstance(size, int) or size < 0:
                errors.append(f"invalid size_bytes for {member}")
            if not isinstance(digest, str) or len(digest) != 64:
                errors.append(f"invalid sha256 for {member}")

        payload_names = sorted(name for name in names if name != MANIFEST_NAME and not name.endswith("/"))
        recorded_names = sorted(records)
        missing_records = sorted(set(payload_names) - set(recorded_names))
        missing_members = sorted(set(recorded_names) - set(payload_names))
        if missing_records:
            errors.append("unrecorded archive members: " + ", ".join(missing_records))
        if missing_members:
            errors.append("manifest files missing from archive: " + ", ".join(missing_members))

        info_by_name = {info.filename: info for info in infos}
        for member, item in records.items():
            info = info_by_name.get(member)
            if info is None:
                continue
            expected_size = item.get("size_bytes")
            if isinstance(expected_size, int) and info.file_size != expected_size:
                errors.append(
                    f"size mismatch for {member}: manifest={expected_size}, archive={info.file_size}"
                )
            expected_sha = item.get("sha256")
            if isinstance(expected_sha, str) and len(expected_sha) == 64:
                with archive.open(info, "r") as stream:
                    actual_sha = sha256_stream(stream)
                if actual_sha != expected_sha:
                    errors.append(f"SHA-256 mismatch for {member}")

        database_present = DATABASE_ARCNAME in records
        storage_present = any(name.startswith("storage/") for name in records)
        exports_present = any(name.startswith("exports/") for name in records)
        expected_presence = {
            "database": database_present,
            "storage": storage_present,
            "exports": exports_present,
        }
        for key, present in expected_presence.items():
            if isinstance(included.get(key), bool) and included[key] != present:
                errors.append(
                    f"included.{key}={included[key]} does not match archived payload presence {present}"
                )

        if database_present:
            with archive.open(DATABASE_ARCNAME, "r") as source:
                database_bytes = source.read()
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp:
                temp.write(database_bytes)
                temp_path = Path(temp.name)
            try:
                if not sqlite_integrity_ok(temp_path):
                    errors.append("archived SQLite database failed PRAGMA integrity_check")
            finally:
                temp_path.unlink(missing_ok=True)

        declared_counts = manifest.get("table_counts")
        if declared_counts is not None and not isinstance(declared_counts, dict):
            errors.append("manifest table_counts must be an object")

    return errors


def safe_extract_backup(backup_path: str | Path, destination: str | Path) -> dict[str, Any]:
    errors = validate_backup(backup_path)
    if errors:
        raise ValueError("backup validation failed: " + "; ".join(errors))
    target = Path(destination).resolve()
    target.mkdir(parents=True, exist_ok=True)
    manifest = load_backup_manifest(backup_path)
    files = manifest.get("files", [])
    with zipfile.ZipFile(Path(backup_path), "r") as archive:
        for item in files:
            member = item["path"]
            relative = PurePosixPath(member)
            output = target.joinpath(*relative.parts).resolve()
            try:
                output.relative_to(target)
            except ValueError as exc:
                raise ValueError(f"archive member escapes extraction root: {member}") from exc
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, output.open("wb") as sink:
                shutil.copyfileobj(source, sink, length=1024 * 1024)
            if output.stat().st_size != item["size_bytes"] or sha256_file(output) != item["sha256"]:
                raise ValueError(f"extracted file failed integrity verification: {member}")
    return manifest


def verify_restored_payload(manifest: dict[str, Any], *, database_path: Path, storage_root: Path, exports_root: Path) -> list[str]:
    errors: list[str] = []
    mapping = {
        DATABASE_ARCNAME: database_path,
    }
    for item in manifest.get("files", []):
        member = item["path"]
        if member == DATABASE_ARCNAME:
            destination = database_path
        elif member.startswith("storage/"):
            destination = storage_root / member.removeprefix("storage/")
        elif member.startswith("exports/"):
            destination = exports_root / member.removeprefix("exports/")
        else:
            errors.append(f"unsupported payload root: {member}")
            continue
        mapping[member] = destination
        if not destination.is_file():
            errors.append(f"restored file missing: {member}")
            continue
        if destination.stat().st_size != item["size_bytes"]:
            errors.append(f"restored size mismatch: {member}")
        if sha256_file(destination) != item["sha256"]:
            errors.append(f"restored SHA-256 mismatch: {member}")
    if manifest.get("included", {}).get("database") and not sqlite_integrity_ok(database_path):
        errors.append("restored SQLite database failed PRAGMA integrity_check")
    return errors
