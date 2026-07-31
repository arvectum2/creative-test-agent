from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class CalibrationCaseEvidence(Base):
    __tablename__ = "calibration_case_evidence"
    __table_args__ = (
        UniqueConstraint("project_id", "case_id", name="uq_calibration_case_project_case"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    evidence_class: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    inclusion_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class CalibrationWorkflowMeasurement(Base):
    __tablename__ = "calibration_workflow_measurement"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    wall_clock_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    operator_touch_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    manual_action_count: Mapped[int] = mapped_column(Integer, nullable=False)
    report_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


@event.listens_for(CalibrationWorkflowMeasurement, "before_update")
def _prevent_workflow_measurement_update(*_):
    raise RuntimeError("CalibrationWorkflowMeasurement is append-only")


@event.listens_for(CalibrationWorkflowMeasurement, "before_delete")
def _prevent_workflow_measurement_delete(*_):
    raise RuntimeError("CalibrationWorkflowMeasurement is append-only and cannot be deleted")
