from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class PilotCaseState(StrEnum):
    included = "included"
    excluded = "excluded"
    deferred = "deferred"
    needs_clarification = "needs_clarification"


class PilotLinkageConfidence(StrEnum):
    exact = "exact"
    probable = "probable"
    uncertain = "uncertain"
    one_to_many = "one_to_many"
    missing = "missing"
    rejected = "rejected"


class PilotCase(Base):
    __tablename__ = "pilot_case"
    __table_args__ = (
        UniqueConstraint("project_id", "case_key", name="uq_pilot_case_project_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    case_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    import_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PilotCaseState.needs_clarification, index=True
    )

    source_package_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_files_json: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_linkage_confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    linkage_confidence: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asset_references_json: Mapped[str] = mapped_column(Text, nullable=False)
    asset_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    reported_impressions: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reported_clicks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reported_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    data_quality_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    data_quality_run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_data_quality_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unavailable", index=True
    )
    warning_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PilotCaseDecision(Base):
    __tablename__ = "pilot_case_decision"
    __table_args__ = (
        UniqueConstraint(
            "pilot_case_id",
            "sequence",
            name="uq_pilot_case_decision_case_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pilot_case_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    case_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


_IMMUTABLE_CASE_FIELDS = (
    "project_id",
    "case_key",
    "import_session_id",
    "source_package_sha256",
    "source_files_json",
    "provenance_json",
    "source_linkage_confidence",
    "linkage_confidence",
    "asset_references_json",
    "asset_count",
    "reported_impressions",
    "reported_clicks",
    "reported_rate",
    "data_quality_snapshot_json",
    "data_quality_run_count",
    "overall_data_quality_status",
    "warning_issue_count",
    "blocking_issue_count",
    "created_by_user_id",
    "created_at",
)


@event.listens_for(PilotCase, "before_update")
def _protect_pilot_case_provenance(_mapper, _connection, target: PilotCase) -> None:
    state = inspect(target)
    changed = [
        field_name
        for field_name in _IMMUTABLE_CASE_FIELDS
        if state.attrs[field_name].history.has_changes()
    ]
    if changed:
        joined = ", ".join(changed)
        raise RuntimeError(f"PilotCase provenance is immutable: {joined}")
    if state.attrs.state.history.has_changes() and not getattr(
        target, "_decision_append_authorized", False
    ):
        raise RuntimeError("PilotCase state changes require an append-only decision")
    target._decision_append_authorized = False


@event.listens_for(PilotCase, "before_delete")
def _prevent_pilot_case_delete(*_) -> None:
    raise RuntimeError("PilotCase is provenance-bound and cannot be deleted")


@event.listens_for(PilotCaseDecision, "before_update")
def _prevent_pilot_decision_update(*_) -> None:
    raise RuntimeError("PilotCaseDecision is append-only")


@event.listens_for(PilotCaseDecision, "before_delete")
def _prevent_pilot_decision_delete(*_) -> None:
    raise RuntimeError("PilotCaseDecision is append-only and cannot be deleted")
