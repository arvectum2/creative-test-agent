from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from src.shared.storage.local_storage import LocalStorage


IMMUTABLE_ORIGINALS_PREFIX = "imports/originals/sha256"


@dataclass(frozen=True)
class StoredOriginal:
    storage_path: str
    sha256: str
    created: bool


class ImmutableOriginalStorage:
    """Content-addressed storage for client files exactly as received."""

    def __init__(self, root: str | None = None):
        self.storage = LocalStorage(root=root)

    def store(self, content: bytes) -> StoredOriginal:
        digest = sha256(content).hexdigest()
        storage_path = f"{IMMUTABLE_ORIGINALS_PREFIX}/{digest[:2]}/{digest}"
        existed = self.storage.exists(storage_path)
        self.storage.store_immutable(storage_path, content, expected_sha256=digest)
        return StoredOriginal(storage_path=storage_path, sha256=digest, created=not existed)

    def absolute_path(self, storage_path: str) -> Path:
        self._validate_storage_path(storage_path)
        return self.storage.absolute_path(storage_path)

    def verify(self, storage_path: str, expected_sha256: str) -> tuple[bool, bool]:
        path = self.absolute_path(storage_path)
        if not path.is_file():
            return False, False
        return True, self._hash_file(path) == expected_sha256

    @staticmethod
    def _validate_storage_path(storage_path: str) -> None:
        prefix = f"{IMMUTABLE_ORIGINALS_PREFIX}/"
        if not storage_path.startswith(prefix):
            raise ValueError("Storage path is outside the immutable originals namespace")
        digest = storage_path.rsplit("/", 1)[-1]
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("Invalid immutable original storage path")

    @staticmethod
    def _hash_file(path: Path) -> str:
        hasher = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
