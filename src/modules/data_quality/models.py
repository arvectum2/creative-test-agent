from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class DataQualityRunStatus(StrEnum):
    completed = "completed"
    failed = "failed"


class DataQualityOverallStatus(StrEnum):
    passed = "passed"
    review_required = "review_required"
    blocked = "blocked"


class DataQualitySeverity(StrEnum):
    info = "info"
    warning = "warning"
    blocking = "blocking"


class DataQualityCategory(StrEnum):
    file_integrity = "file_integrity"
    schema_detection = "schema_detection"
    mapping = "mapping"
    missing_values = "missing_values"
    duplicates = "duplicates"
    creative_linking = "creative_linking"
    metric_consistency = "metric_consistency"
    prediction_readiness = "prediction_readiness"


class DataQualityRun(Base):
    __tablename__ = "data_quality_run"
    __table_args__ = (
        UniqueConstraint(
            "source_table_id",
            "engine_version",
            "input_fingerprint",
            "run_number",
            name="uq_data_quality_run_table_version_fingerprint_number",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    import_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalization_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=DataQualityRunStatus.completed, index=True
    )
    overall_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=DataQualityOverallStatus.passed, index=True
    )

    source_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    confirmed_mapping_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suggested_mapping_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_mapping_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmapped_mapping_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    normalized_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partial_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    creative_record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    linked_creative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unlinked_creative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ambiguous_creative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    performance_observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    info_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    category_counts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issue"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    data_quality_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False, default="run", index=True)
    scope_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_table_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_row_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_column_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    remediation_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
