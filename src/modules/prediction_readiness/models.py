from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class PredictionReadinessRunStatus(StrEnum):
    completed = "completed"
    failed = "failed"


class PredictionReadinessOverallStatus(StrEnum):
    ready = "ready"
    degraded = "degraded"
    unavailable = "unavailable"


class CapabilityStatus(StrEnum):
    ready = "ready"
    degraded = "degraded"
    unavailable = "unavailable"
    not_applicable = "not_applicable"


class EvidenceStrength(StrEnum):
    strong = "strong"
    moderate = "moderate"
    weak = "weak"
    none = "none"


class PredictionReadinessRun(Base):
    __tablename__ = "prediction_readiness_run"
    __table_args__ = (
        UniqueConstraint(
            "data_quality_run_id",
            "evaluator_version",
            "input_fingerprint",
            "run_number",
            name="uq_prediction_readiness_run_input_version_number",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    data_quality_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    import_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluator_name: Mapped[str] = mapped_column(String(100), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=PredictionReadinessRunStatus.completed, index=True
    )
    overall_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=PredictionReadinessOverallStatus.unavailable, index=True
    )
    capability_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    degraded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unavailable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_applicable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_client_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_analyst_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class PredictionCapabilityReadiness(Base):
    __tablename__ = "prediction_capability_readiness"
    __table_args__ = (
        UniqueConstraint(
            "prediction_readiness_run_id",
            "capability_key",
            name="uq_prediction_capability_run_key",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    prediction_readiness_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    capability_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    internal_message: Mapped[str] = mapped_column(Text, nullable=False)
    reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_inputs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_inputs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    degraded_inputs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_operations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    prohibited_operations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
