from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class ClarificationAudience(StrEnum):
    client = "client"
    analyst = "analyst"


class ClarificationRunStatus(StrEnum):
    open = "open"
    resolved = "resolved"


class ClarificationQuestionStatus(StrEnum):
    open = "open"
    answered = "answered"
    deferred = "deferred"
    not_available = "not_available"
    not_applicable = "not_applicable"


class ClarificationPriority(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"


class ClarificationAnswerType(StrEnum):
    single_choice = "single_choice"
    multiple_choice = "multiple_choice"
    text = "text"
    boolean = "boolean"
    integer = "integer"


class ClarificationRun(Base):
    __tablename__ = "clarification_run"
    __table_args__ = (
        UniqueConstraint(
            "source_table_id",
            "generator_version",
            "input_fingerprint",
            "run_number",
            name="uq_clarification_run_table_version_fingerprint_number",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    data_quality_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    import_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    generator_name: Mapped[str] = mapped_column(String(100), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    audience: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    max_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ClarificationRunStatus.open, index=True
    )
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suppressed_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answered_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deferred_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_available_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_applicable_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClarificationQuestion(Base):
    __tablename__ = "clarification_question"
    __table_args__ = (
        UniqueConstraint(
            "clarification_run_id",
            "question_key",
            name="uq_clarification_question_run_key",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    clarification_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    question_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    audience: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    why_needed: Mapped[str] = mapped_column(Text, nullable=False)
    answer_type: Mapped[str] = mapped_column(String(50), nullable=False)
    options_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    impact_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ClarificationQuestionStatus.open, index=True
    )
    latest_response_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClarificationResponse(Base):
    __tablename__ = "clarification_response"
    __table_args__ = (
        UniqueConstraint(
            "clarification_question_id",
            "response_number",
            name="uq_clarification_response_question_number",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    clarification_question_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    response_number: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    answer_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
