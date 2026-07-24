from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text, event
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

    @property
    def content_type(self) -> str | None:
        """Backward-compatible report alias for the declared MIME type."""
        return self.declared_mime_type

    @property
    def duplicate_of_file_id(self) -> None:
        """Physical deduplication does not collapse provenance records."""
        return None


class SourceInspectionStatus(StrEnum):
    running = "running"
    completed = "completed"
    failed = "failed"


class SourceInspection(Base):
    __tablename__ = "source_inspection"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    import_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    inspection_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=SourceInspectionStatus.running, index=True
    )
    parser_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    file_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    encoding: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delimiter: Mapped[str | None] = mapped_column(String(10), nullable=True)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SourceTable(Base):
    __tablename__ = "source_table"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    inspection_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    header_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    header_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SourceColumn(Base):
    __tablename__ = "source_column"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_header: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_header: Mapped[str] = mapped_column(String(255), nullable=False)
    inferred_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_empty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    duplicate_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    non_empty_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sample_values_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SourceRow(Base):
    __tablename__ = "source_row"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    values_json: Mapped[str] = mapped_column(Text, nullable=False)
    cell_types_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def _reject_source_file_mutation(_mapper, _connection, target: ImportSourceFile) -> None:
    raise RuntimeError(
        f"Import source file {target.id!r} is immutable; create a new import record instead"
    )


event.listen(ImportSourceFile, "before_update", _reject_source_file_mutation)
event.listen(ImportSourceFile, "before_delete", _reject_source_file_mutation)
