from datetime import datetime

from pydantic import BaseModel, Field


class GenerateDataReviewReportRequest(BaseModel):
    prediction_readiness_run_id: str | None = None
    quantitative_study_id: str | None = None
    force: bool = False


class DataReviewReportResponse(BaseModel):
    id: str
    data_quality_run_id: str
    prediction_readiness_run_id: str | None = None
    quantitative_study_id: str | None = None
    source_table_id: str
    source_file_id: str
    import_session_id: str
    project_id: str
    run_number: int
    generator_name: str
    generator_version: str
    input_fingerprint: str
    status: str
    filename: str
    sha256: str
    file_size_bytes: int
    sheet_count: int
    summary: dict = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime | None = None
