from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GenerateClarificationsRequest(BaseModel):
    audience: str = "client"
    max_questions: int = Field(default=5, ge=3, le=5)
    force: bool = False


class SubmitClarificationResponseRequest(BaseModel):
    resolution: str = "answered"
    answer: Any | None = None
    note: str | None = Field(default=None, max_length=4000)


class ClarificationResponseResponse(BaseModel):
    id: str
    clarification_question_id: str
    response_number: int
    resolution: str
    answer: Any | None = None
    note: str | None = None
    responded_by_user_id: str | None = None
    created_at: datetime | None = None


class ClarificationQuestionResponse(BaseModel):
    id: str
    clarification_run_id: str
    question_key: str
    rank: int
    priority_score: int
    priority: str
    category: str
    audience: str
    question_text: str
    why_needed: str
    answer_type: str
    options: list[dict] = Field(default_factory=list)
    issue_codes: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    impact: dict = Field(default_factory=dict)
    status: str
    latest_response: ClarificationResponseResponse | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_at: datetime | None = None


class ClarificationRunResponse(BaseModel):
    id: str
    data_quality_run_id: str
    source_table_id: str
    source_file_id: str
    import_session_id: str
    project_id: str
    run_number: int
    generator_name: str
    generator_version: str
    input_fingerprint: str
    audience: str
    max_questions: int
    status: str
    candidate_count: int
    question_count: int
    suppressed_question_count: int
    open_question_count: int
    answered_question_count: int
    deferred_question_count: int
    not_available_question_count: int
    not_applicable_question_count: int
    summary: dict = Field(default_factory=dict)
    created_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_at: datetime | None = None


class ClarificationResultResponse(BaseModel):
    run: ClarificationRunResponse
    questions: list[ClarificationQuestionResponse] = Field(default_factory=list)


class ClarificationQuestionPageResponse(BaseModel):
    clarification_run_id: str
    offset: int
    limit: int
    total: int
    questions: list[ClarificationQuestionResponse] = Field(default_factory=list)


class ClarificationResponsePageResponse(BaseModel):
    clarification_question_id: str
    total: int
    responses: list[ClarificationResponseResponse] = Field(default_factory=list)
