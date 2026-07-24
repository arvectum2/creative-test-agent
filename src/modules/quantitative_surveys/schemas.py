from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QuestionConfig(BaseModel):
    code: str
    prompt: str
    question_type: str
    metric_key: str
    required: bool = True
    scale_min: float | None = None
    scale_max: float | None = None
    low_label: str | None = None
    high_label: str | None = None
    options: list[str] = Field(default_factory=list)
    reverse_scored: bool = False


class CreateQuestionnaireRequest(BaseModel):
    project_id: str
    name: str
    description: str | None = None
    locale: str = "en"
    randomize_questions: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    questions: list[QuestionConfig]


class CreateStudyRequest(BaseModel):
    project_id: str
    questionnaire_id: str
    name: str
    target_response_count: int = Field(ge=1, le=10000)
    creative_asset_ids: list[str]
    randomize_creatives: bool = True
    seed: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudyAnswerInput(BaseModel):
    question_code: str
    value: Any


class SubmitStudyResponseRequest(BaseModel):
    respondent_key: str
    creative_asset_id: str
    source: str = "human"
    generation_provenance: dict[str, Any] = Field(default_factory=dict)
    answers: list[StudyAnswerInput]


class SimulateStudyRequest(BaseModel):
    respondent_count: int = Field(ge=1, le=500)
    seed: int | None = None
    creative_effects: dict[str, float] = Field(default_factory=dict)


class QuestionResponse(BaseModel):
    id: str
    questionnaire_id: str
    position: int
    code: str
    prompt: str
    question_type: str
    metric_key: str
    required: bool
    scale_min: float | None = None
    scale_max: float | None = None
    low_label: str | None = None
    high_label: str | None = None
    options: list[str] = Field(default_factory=list)
    reverse_scored: bool


class QuestionnaireResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None = None
    version: int
    status: str
    locale: str
    randomize_questions: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    published_at: datetime | None = None
    created_by_user_id: str | None = None
    created_at: datetime | None = None
    questions: list[QuestionResponse] = Field(default_factory=list)


class StudyResponse(BaseModel):
    id: str
    project_id: str
    questionnaire_id: str
    name: str
    status: str
    target_response_count: int
    response_count: int
    creative_asset_ids: list[str]
    randomize_creatives: bool
    seed: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    created_by_user_id: str | None = None
    created_at: datetime | None = None


class SubmittedResponse(BaseModel):
    id: str
    study_id: str
    respondent_hash: str
    creative_asset_id: str
    source: str
    completed_at: datetime | None = None


class StudyResultsResponse(BaseModel):
    study: StudyResponse
    questionnaire: QuestionnaireResponse
    total_responses: int
    source_counts: dict[str, int] = Field(default_factory=dict)
    metric_keys: list[str] = Field(default_factory=list)
    by_creative: dict[str, dict[str, Any]] = Field(default_factory=dict)
    question_results: list[dict[str, Any]] = Field(default_factory=list)
    interpretation_notes: list[str] = Field(default_factory=list)
