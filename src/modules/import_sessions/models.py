from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class ImportSessionStatus(StrEnum):
    open = "open"
    completed = "completed"


class ImportSession(Base):
    __tablename__ = "import_session"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ImportSessionStatus.open, index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, onupdate=lambda: datetime.now(timezone.utc)
    )


class ImportSourceFile(Base):
    __tablename__ = "import_source_file"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    import_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    extension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    declared_mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def _reject_source_file_mutation(_mapper, _connection, target: ImportSourceFile) -> None:
    raise RuntimeError(
        f"Import source file {target.id!r} is immutable; create a new import record instead"
    )


event.listen(ImportSourceFile, "before_update", _reject_source_file_mutation)
event.listen(ImportSourceFile, "before_delete", _reject_source_file_mutation)
