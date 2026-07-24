from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class NormalizationRunStatus(StrEnum):
    completed = "completed"
    failed = "failed"


class NormalizedRowStatus(StrEnum):
    normalized = "normalized"
    partial = "partial"
    skipped = "skipped"
    failed = "failed"


class NormalizationRun(Base):
    __tablename__ = "normalization_run"
    __table_args__ = (
        UniqueConstraint(
            "source_table_id",
            "normalizer_version",
            "mapping_fingerprint",
            "run_number",
            name="uq_normalization_run_table_version_fingerprint_number",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    import_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    normalizer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(50), nullable=False)
    mapping_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mapping_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=NormalizationRunStatus.completed, index=True
    )
    source_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partial_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    campaign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    creative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    platform_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audience_segment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    placement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    performance_observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Campaign(Base):
    __tablename__ = "normalized_campaign"
    __table_args__ = (
        UniqueConstraint(
            "normalization_run_id",
            "reference_key",
            name="uq_normalized_campaign_run_reference",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    normalization_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reference_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(512), nullable=True)
    product: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CreativeRecord(Base):
    __tablename__ = "normalized_creative_record"
    __table_args__ = (
        UniqueConstraint(
            "normalization_run_id",
            "reference_key",
            name="uq_normalized_creative_run_reference",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    normalization_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reference_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    display_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    creative_asset_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Platform(Base):
    __tablename__ = "normalized_platform"
    __table_args__ = (
        UniqueConstraint(
            "normalization_run_id",
            "canonical_key",
            name="uq_normalized_platform_run_key",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    normalization_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    canonical_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AudienceSegment(Base):
    __tablename__ = "normalized_audience_segment"
    __table_args__ = (
        UniqueConstraint(
            "normalization_run_id",
            "canonical_key",
            name="uq_normalized_audience_run_key",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    normalization_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    canonical_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Placement(Base):
    __tablename__ = "normalized_placement"
    __table_args__ = (
        UniqueConstraint(
            "normalization_run_id",
            "source_row_id",
            name="uq_normalized_placement_run_source_row",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    normalization_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    creative_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    platform_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    audience_segment_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    placement_type: Mapped[str | None] = mapped_column(String(512), nullable=True)
    format: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class PerformanceObservation(Base):
    __tablename__ = "normalized_performance_observation"
    __table_args__ = (
        UniqueConstraint(
            "normalization_run_id",
            "source_row_id",
            name="uq_normalized_performance_run_source_row",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    normalization_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    placement_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    observation_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    impressions: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    clicks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class NormalizedSourceRow(Base):
    __tablename__ = "normalized_source_row"
    __table_args__ = (
        UniqueConstraint(
            "normalization_run_id",
            "source_row_id",
            name="uq_normalized_source_row_run_source_row",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    normalization_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=NormalizedRowStatus.normalized, index=True
    )
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    custom_fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    campaign_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    creative_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    platform_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    audience_segment_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    placement_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    performance_observation_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class NormalizedFieldValue(Base):
    __tablename__ = "normalized_field_value"
    __table_args__ = (
        UniqueConstraint(
            "normalization_run_id",
            "source_row_id",
            "field_name",
            name="uq_normalized_field_run_row_field",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    normalization_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_source_row_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_column_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_column_name: Mapped[str] = mapped_column(String(512), nullable=False)
    column_mapping_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    mapping_profile_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    normalization_version: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_value_json: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    transformation: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
