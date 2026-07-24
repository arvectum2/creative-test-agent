from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class QuestionnaireStatus(StrEnum):
    draft = "draft"
    published = "published"
    archived = "archived"


class QuestionType(StrEnum):
    likert = "likert"
    numeric = "numeric"
    yes_no = "yes_no"
    single_choice = "single_choice"
    multiple_choice = "multiple_choice"


class StudyStatus(StrEnum):
    draft = "draft"
    open = "open"
    closed = "closed"


class ResponseSource(StrEnum):
    human = "human"
    imported = "imported"
    synthetic = "synthetic"


class QuantitativeQuestionnaire(Base):
    __tablename__ = "quantitative_questionnaire"
    __table_args__ = (
        UniqueConstraint("project_id", "name", "version", name="uq_quant_questionnaire_project_name_version"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=QuestionnaireStatus.draft, index=True)
    locale: Mapped[str] = mapped_column(String(20), nullable=False, default="en")
    randomize_questions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class QuantitativeQuestion(Base):
    __tablename__ = "quantitative_question"
    __table_args__ = (
        UniqueConstraint("questionnaire_id", "code", name="uq_quant_questionnaire_question_code"),
        UniqueConstraint("questionnaire_id", "position", name="uq_quant_questionnaire_question_position"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    questionnaire_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scale_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    scale_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    high_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    options_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reverse_scored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class QuantitativeStudy(Base):
    __tablename__ = "quantitative_study"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    questionnaire_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=StudyStatus.draft, index=True)
    target_response_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    creative_asset_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    randomize_creatives: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class QuantitativeResponse(Base):
    __tablename__ = "quantitative_response"
    __table_args__ = (
        UniqueConstraint("study_id", "respondent_hash", name="uq_quant_response_study_respondent"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    study_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    respondent_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    creative_asset_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    generation_provenance_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class QuantitativeAnswer(Base):
    __tablename__ = "quantitative_answer"
    __table_args__ = (
        UniqueConstraint("response_id", "question_id", name="uq_quant_answer_response_question"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    response_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    selected_values_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
