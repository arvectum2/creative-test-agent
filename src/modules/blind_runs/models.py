from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class BlindDiagnosticRevision(Base):
    __tablename__ = "blind_diagnostic_revision"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "pilot_case_id",
            "revision_number",
            name="uq_blind_diag_project_case_revision",
        ),
        UniqueConstraint(
            "project_id",
            "pilot_case_id",
            "execution_id",
            name="uq_blind_diag_project_case_execution",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pilot_case_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    case_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    supersedes_revision_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    previous_revision_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    diagnostic_output_json: Mapped[str] = mapped_column(Text, nullable=False)
    diagnostic_output_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    input_provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_provenance_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    prompt_manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_manifest_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    model_profile_json: Mapped[str] = mapped_column(Text, nullable=False)
    model_profile_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    code_revision: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    execution_metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    execution_metadata_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    revision_manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    revision_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class BlindOutcomeEnvelope(Base):
    __tablename__ = "blind_outcome_envelope"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "pilot_case_id",
            name="uq_blind_outcome_project_case",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pilot_case_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    case_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    outcome_schema_version: Mapped[str] = mapped_column(String(120), nullable=False)
    outcome_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_payload_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


@event.listens_for(BlindDiagnosticRevision, "before_update")
def _prevent_blind_revision_update(*_) -> None:
    raise RuntimeError(
        "BlindDiagnosticRevision is frozen and append-only; create a rerun revision instead"
    )


@event.listens_for(BlindDiagnosticRevision, "before_delete")
def _prevent_blind_revision_delete(*_) -> None:
    raise RuntimeError("BlindDiagnosticRevision is frozen and cannot be deleted")


@event.listens_for(BlindOutcomeEnvelope, "before_update")
def _prevent_outcome_envelope_update(*_) -> None:
    raise RuntimeError("BlindOutcomeEnvelope is sealed and immutable")


@event.listens_for(BlindOutcomeEnvelope, "before_delete")
def _prevent_outcome_envelope_delete(*_) -> None:
    raise RuntimeError("BlindOutcomeEnvelope is sealed and cannot be deleted")
