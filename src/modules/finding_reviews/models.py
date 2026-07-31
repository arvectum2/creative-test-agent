from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class FindingReview(Base):
    __tablename__ = "finding_review"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "finding_id",
            "revision_number",
            name="uq_finding_review_project_finding_revision",
        ),
        UniqueConstraint(
            "project_id",
            "finding_id",
            "reviewer_subject_id",
            "reviewer_revision_number",
            name="uq_finding_review_project_finding_reviewer_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    case_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    creative_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    creative_asset_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    test_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    finding_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    system_finding_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_finding_snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    human_finding_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_finding_snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    reviewer_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    reviewer_subject_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reviewer_subject_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewer_role: Mapped[str] = mapped_column(String(160), nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    correctness: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance: Mapped[int] = mapped_column(Integer, nullable=False)
    actionability: Mapped[int] = mapped_column(Integer, nullable=False)
    traceability: Mapped[int] = mapped_column(Integer, nullable=False)
    severity_correctness: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewer_revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_review_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class FindingAdjudication(Base):
    __tablename__ = "finding_adjudication"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "finding_id",
            "adjudication_round",
            name="uq_finding_adjudication_project_finding_round",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    case_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    creative_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    creative_asset_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    test_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    finding_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    policy_id: Mapped[str] = mapped_column(String(120), nullable=False)

    basis_review_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    basis_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    adjudicator_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    adjudicator_subject_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    adjudicator_subject_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    adjudicator_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    adjudicator_role: Mapped[str] = mapped_column(String(160), nullable=False)

    decision: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    correctness: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance: Mapped[int] = mapped_column(Integer, nullable=False)
    actionability: Mapped[int] = mapped_column(Integer, nullable=False)
    traceability: Mapped[int] = mapped_column(Integer, nullable=False)
    severity_correctness: Mapped[str] = mapped_column(String(32), nullable=False)
    adjudicator_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    adjudication_round: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_adjudication_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


@event.listens_for(FindingReview, "before_update")
def _prevent_finding_review_update(*_):
    raise RuntimeError("FindingReview is append-only; create a new revision instead")


@event.listens_for(FindingReview, "before_delete")
def _prevent_finding_review_delete(*_):
    raise RuntimeError("FindingReview is append-only and cannot be deleted")


@event.listens_for(FindingAdjudication, "before_update")
def _prevent_finding_adjudication_update(*_):
    raise RuntimeError("FindingAdjudication is append-only; create a new round instead")


@event.listens_for(FindingAdjudication, "before_delete")
def _prevent_finding_adjudication_delete(*_):
    raise RuntimeError("FindingAdjudication is append-only and cannot be deleted")
