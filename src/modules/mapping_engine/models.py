from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class MappingRunStatus(StrEnum):
    completed = "completed"
    failed = "failed"


class ColumnMappingStatus(StrEnum):
    suggested = "suggested"
    confirmed = "confirmed"
    rejected = "rejected"
    unmapped = "unmapped"


class MappingProfileStatus(StrEnum):
    active = "active"
    archived = "archived"


class MappingRun(Base):
    __tablename__ = "mapping_run"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    import_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    mapping_profile_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=MappingRunStatus.completed, index=True
    )
    suggestion_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MappingSuggestion(Base):
    __tablename__ = "mapping_suggestion"
    __table_args__ = (
        UniqueConstraint(
            "mapping_run_id",
            "source_column_id",
            "target_field",
            name="uq_mapping_suggestion_run_column_target",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    mapping_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_column_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_field: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    explanation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ColumnMapping(Base):
    __tablename__ = "column_mapping"
    __table_args__ = (
        UniqueConstraint("source_column_id", name="uq_column_mapping_source_column"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_column_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_field: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ColumnMappingStatus.unmapped, index=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_source: Mapped[str] = mapped_column(String(50), nullable=False, default="engine")
    selected_suggestion_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping_profile_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    rationale_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, onupdate=lambda: datetime.now(timezone.utc)
    )


class MappingProfile(Base):
    __tablename__ = "mapping_profile"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sheet_name_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=MappingProfileStatus.active, index=True
    )
    created_from_table_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, onupdate=lambda: datetime.now(timezone.utc)
    )


class MappingProfileRule(Base):
    __tablename__ = "mapping_profile_rule"
    __table_args__ = (
        UniqueConstraint(
            "mapping_profile_id",
            "source_key",
            name="uq_mapping_profile_rule_profile_source_key",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    mapping_profile_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_header: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_inferred_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_field: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_from_column_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
