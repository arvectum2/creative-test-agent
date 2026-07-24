from datetime import datetime

from pydantic import BaseModel, Field


class GenerateDataQualityRequest(BaseModel):
    force: bool = False


class DataQualityIssueResponse(BaseModel):
    id: str
    data_quality_run_id: str
    category: str
    code: str
    severity: str
    scope_type: str
    scope_id: str | None = None
    source_file_id: str | None = None
    source_table_id: str | None = None
    source_row_id: str | None = None
    source_column_id: str | None = None
    affected_count: int
    message: str
    remediation_hint: str | None = None
    details: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class DataQualityRunResponse(BaseModel):
    id: str
    source_table_id: str
    source_file_id: str
    import_session_id: str
    project_id: str
    normalization_run_id: str | None = None
    run_number: int
    engine_name: str
    engine_version: str
    input_fingerprint: str
    status: str
    overall_status: str

    source_file_count: int
    source_table_count: int
    source_row_count: int
    source_column_count: int

    confirmed_mapping_count: int
    suggested_mapping_count: int
    rejected_mapping_count: int
    unmapped_mapping_count: int

    normalized_row_count: int
    partial_row_count: int
    skipped_row_count: int
    failed_row_count: int

    creative_record_count: int
    linked_creative_count: int
    unlinked_creative_count: int
    ambiguous_creative_count: int
    performance_observation_count: int

    info_issue_count: int
    warning_issue_count: int
    blocking_issue_count: int
    total_issue_count: int

    category_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    summary: dict = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime | None = None


class DataQualityResultResponse(BaseModel):
    run: DataQualityRunResponse
    issues: list[DataQualityIssueResponse] = Field(default_factory=list)


class DataQualityIssuePageResponse(BaseModel):
    data_quality_run_id: str
    offset: int
    limit: int
    total: int
    issues: list[DataQualityIssueResponse] = Field(default_factory=list)
