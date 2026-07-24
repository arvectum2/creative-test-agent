from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class NormalizeTableRequest(BaseModel):
    force: bool = False


class NormalizationRunResponse(BaseModel):
    id: str
    source_table_id: str
    source_file_id: str
    import_session_id: str
    project_id: str
    run_number: int
    normalizer_name: str
    normalizer_version: str
    mapping_fingerprint: str
    mapping_snapshot: list[dict] = Field(default_factory=list)
    status: str
    source_row_count: int
    normalized_row_count: int
    partial_row_count: int
    skipped_row_count: int
    failed_row_count: int
    campaign_count: int
    creative_count: int
    platform_count: int
    audience_segment_count: int
    placement_count: int
    performance_observation_count: int
    warning_count: int
    warnings: list[dict] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime | None = None


class CampaignResponse(BaseModel):
    id: str
    normalization_run_id: str
    project_id: str
    reference_key: str | None = None
    brand: str | None = None
    product: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class CreativeRecordResponse(BaseModel):
    id: str
    normalization_run_id: str
    project_id: str
    reference_key: str
    display_reference: str | None = None
    creative_asset_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class PlatformResponse(BaseModel):
    id: str
    normalization_run_id: str
    project_id: str
    canonical_key: str
    name: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class AudienceSegmentResponse(BaseModel):
    id: str
    normalization_run_id: str
    project_id: str
    canonical_key: str
    name: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class PlacementResponse(BaseModel):
    id: str
    normalization_run_id: str
    project_id: str
    source_row_id: str
    campaign_id: str | None = None
    creative_record_id: str | None = None
    platform_id: str | None = None
    audience_segment_id: str | None = None
    placement_type: str | None = None
    format: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class PerformanceObservationResponse(BaseModel):
    id: str
    normalization_run_id: str
    project_id: str
    source_row_id: str
    placement_id: str | None = None
    observation_date: date | None = None
    impressions: int | None = None
    clicks: int | None = None
    ctr: float | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class NormalizedFieldValueResponse(BaseModel):
    id: str
    normalization_run_id: str
    normalized_source_row_id: str
    entity_type: str
    entity_id: str
    field_name: str
    source_file_id: str
    source_table_id: str
    source_row_id: str
    source_row_number: int
    source_column_id: str
    source_column_name: str
    column_mapping_id: str
    mapping_profile_id: str | None = None
    normalization_version: str
    raw_value: object | None = None
    normalized_value: object | None = None
    transformation: str
    created_at: datetime | None = None

    @model_validator(mode="after")
    def normalize_missing_scalar(self):
        if self.transformation == "parse_failed" and self.normalized_value == {}:
            self.normalized_value = None
        return self


class NormalizedSourceRowResponse(BaseModel):
    id: str
    normalization_run_id: str
    project_id: str
    source_file_id: str
    source_table_id: str
    source_row_id: str
    source_row_number: int
    status: str
    issue_count: int
    issues: list[dict] = Field(default_factory=list)
    source_payload: dict = Field(default_factory=dict)
    custom_fields: dict = Field(default_factory=dict)
    campaign_id: str | None = None
    creative_record_id: str | None = None
    platform_id: str | None = None
    audience_segment_id: str | None = None
    placement_id: str | None = None
    performance_observation_id: str | None = None
    field_values: list[NormalizedFieldValueResponse] = Field(default_factory=list)
    created_at: datetime | None = None


class NormalizedSourceRowPageResponse(BaseModel):
    normalization_run_id: str
    offset: int
    limit: int
    total: int
    rows: list[NormalizedSourceRowResponse] = Field(default_factory=list)


class NormalizationResultResponse(BaseModel):
    run: NormalizationRunResponse
    rows: list[NormalizedSourceRowResponse] = Field(default_factory=list)
