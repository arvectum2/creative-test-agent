from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class GenerateClientOnePageReportRequest(BaseModel):
    prediction_readiness_run_id: str | None = None
    quantitative_study_id: str | None = None
    locale: Literal["ru", "en"] = "ru"
    force: bool = False


class ClientOnePageArtifactResponse(BaseModel):
    artifact_type: Literal["pptx", "html", "evidence"]
    filename: str
    media_type: str
    sha256: str
    size_bytes: int


class ClientOnePageReportResponse(BaseModel):
    id: str
    data_quality_run_id: str
    prediction_readiness_run_id: str
    quantitative_study_id: str | None = None
    source_table_id: str
    source_file_id: str
    import_session_id: str
    project_id: str
    client_id: str | None = None
    run_number: int
    generator_name: str
    generator_version: str
    input_fingerprint: str
    status: str
    locale: str
    verdict: str
    title: str
    slide_count: int
    artifacts: list[ClientOnePageArtifactResponse]
    manifest_filename: str
    manifest_sha256: str
    manifest_size_bytes: int
    summary: dict[str, Any] = Field(default_factory=dict)
    created_by_user_id: str | None = None
    created_at: datetime
