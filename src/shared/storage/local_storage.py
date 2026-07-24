import hashlib
import os
import re
import shutil
import uuid
from pathlib import Path

from src.shared.config.settings import get_settings


class LocalStorage:
    def __init__(self, root: str | None = None):
        settings = get_settings()
        self.root = Path(root or settings.storage_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def safe_store(self, content: bytes, ext: str) -> str:
        name = f"{uuid.uuid4().hex}{ext}"
        return self.store(name, content)

    def store(self, path: str, content: bytes) -> str:
        safe = self._sanitize_path(path)
        full_path = self.root / safe
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return str(full_path)

    def store_immutable(
        self,
        path: str,
        content: bytes,
        expected_sha256: str | None = None,
    ) -> str:
        """Create a file once and never replace existing bytes.

        A concurrent or repeated write is accepted only when the existing file
        has the same SHA-256 digest as *content*.
        """
        safe = self._sanitize_path(path)
        if not safe:
            raise ValueError("Immutable storage path must not be empty")
        full_path = self.root / safe
        full_path.parent.mkdir(parents=True, exist_ok=True)
        content_sha256 = hashlib.sha256(content).hexdigest()
        if expected_sha256 and content_sha256 != expected_sha256:
            raise ValueError("Content checksum does not match expected SHA-256")

        try:
            descriptor = os.open(
                full_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            existing_sha256 = self._sha256_file(full_path)
            if existing_sha256 != content_sha256:
                raise ValueError(
                    "Immutable storage path already exists with different content"
                )
            return str(full_path)

        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            full_path.unlink(missing_ok=True)
            raise
        return str(full_path)

    def read(self, path: str) -> bytes:
        safe = self._sanitize_path(path)
        return (self.root / safe).read_bytes()

    def delete(self, path: str) -> None:
        safe = self._sanitize_path(path)
        full_path = self.root / safe
        if full_path.is_file():
            full_path.unlink()
        elif full_path.is_dir():
            shutil.rmtree(str(full_path))

    def exists(self, path: str) -> bool:
        safe = self._sanitize_path(path)
        return (self.root / safe).exists()

    def absolute_path(self, relative_path: str) -> Path:
        safe = self._sanitize_path(relative_path)
        return self.root / safe

    @staticmethod
    def _sha256_file(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _sanitize_path(path: str) -> str:
        cleaned = path.lstrip("/")
        parts = []
        for part in cleaned.split("/"):
            if part in ("", ".", ".."):
                continue
            parts.append(part)
        result = "/".join(parts)
        result = re.sub(r"[^\w\-./]", "_", result)
        return result
