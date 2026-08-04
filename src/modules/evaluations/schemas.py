from datetime import datetime

from pydantic import BaseModel, Field


class EvaluationCaseResultResponse(BaseModel):
    id: str
    evaluation_run_id: str
    case_id: str
    status: str
    score: int
    passed: int
    total_checks: int
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    output_summary: dict = Field(default_factory=dict)
    created_at: datetime


class EvaluationRunResponse(BaseModel):
    id: str
    profile_id: str | None = None
    provider: str
    model: str
    status: str
    summary: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    results: list[EvaluationCaseResultResponse] = Field(default_factory=list)
class RunEvaluationRequest(BaseModel):
    profile_id: str | None = None
    case_ids: list[str] | None = None
    mode: str = "stub"
