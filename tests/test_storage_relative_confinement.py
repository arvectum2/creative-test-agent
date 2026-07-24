from pathlib import Path

import pytest

from src.shared.security.hardening import ensure_within_root


def test_relative_storage_path_resolves_from_configured_root(tmp_path: Path):
    root = tmp_path / "storage"
    root.mkdir()

    resolved = ensure_within_root("imports/originals/sha256/aa/example", root)

    assert resolved == (root / "imports/originals/sha256/aa/example").resolve()


def test_relative_storage_path_cannot_escape_configured_root(tmp_path: Path):
    root = tmp_path / "storage"
    root.mkdir()

    with pytest.raises(ValueError):
        ensure_within_root("../outside.txt", root)
