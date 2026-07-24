from datetime import datetime

from pydantic import BaseModel, Field


class GeneratePredictionReadinessRequest(BaseModel):
    force: bool = False


class PredictionCapabilityResponse(BaseModel):
    id: str
    prediction_readiness_run_id: str
    capability_key: str
    status: str
    mode: str
    evidence_strength: str
    title: str
    user_message: str
    internal_message: str
    reasons: list[dict] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    degraded_inputs: list[str] = Field(default_factory=list)
    allowed_operations: list[str] = Field(default_factory=list)
    prohibited_operations: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class PredictionReadinessRunResponse(BaseModel):
    id: str
    data_quality_run_id: str
    source_table_id: str
    source_file_id: str
    import_session_id: str
    project_id: str
    run_number: int
    evaluator_name: str
    evaluator_version: str
    input_fingerprint: str
    status: str
    overall_status: str
    capability_count: int
    ready_count: int
    degraded_count: int
    unavailable_count: int
    not_applicable_count: int
    unresolved_client_question_count: int
    unresolved_analyst_question_count: int
    summary: dict = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime | None = None


class PredictionReadinessResultResponse(BaseModel):
    run: PredictionReadinessRunResponse
    capabilities: list[PredictionCapabilityResponse] = Field(default_factory=list)
