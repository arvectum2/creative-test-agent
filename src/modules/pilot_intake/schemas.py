from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

PilotState = Literal["included", "excluded", "deferred", "needs_clarification"]
LinkageConfidence = Literal[
    "exact",
    "probable",
    "uncertain",
    "one_to_many",
    "missing",
    "rejected",
]
DataQualityStatus = Literal["passed", "review_required", "blocked", "unavailable"]


class PilotMetricEvidence(BaseModel):
    impressions: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)
    rate: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_counts(self):
        if (
            self.impressions is not None
            and self.clicks is not None
            and self.clicks > self.impressions
        ):
            raise ValueError("clicks cannot exceed impressions")
        return self


class RegisterPilotCaseRequest(BaseModel):
    case_key: str = Field(min_length=1, max_length=255)
    import_session_id: str = Field(min_length=1, max_length=255)
    initial_state: PilotState = "needs_clarification"
    source_linkage_confidence: LinkageConfidence
    requested_linkage_confidence: LinkageConfidence | None = None
    asset_references: list[str] = Field(default_factory=list, max_length=1000)
    metrics: PilotMetricEvidence = Field(default_factory=PilotMetricEvidence)
    data_quality_run_ids: list[str] = Field(default_factory=list, max_length=1000)
    provenance: dict[str, Any] = Field(default_factory=dict)
    decision_reason: str = Field(default="case_registered", min_length=1, max_length=4000)


class PilotSourceFileEvidence(BaseModel):
    source_file_id: str
    original_filename: str
    file_size_bytes: int
    sha256: str


class PilotDataQualityRunEvidence(BaseModel):
    run_id: str
    source_table_id: str
    input_fingerprint: str
    overall_status: DataQualityStatus
    confirmed_mapping_count: int
    suggested_mapping_count: int
    rejected_mapping_count: int
    unmapped_mapping_count: int
    warning_issue_count: int
    blocking_issue_count: int
    total_issue_count: int


class PilotDataQualitySnapshot(BaseModel):
    overall_status: DataQualityStatus
    run_count: int
    confirmed_mapping_count: int
    suggested_mapping_count: int
    rejected_mapping_count: int
    unmapped_mapping_count: int
    warning_issue_count: int
    blocking_issue_count: int
    total_issue_count: int
    runs: list[PilotDataQualityRunEvidence] = Field(default_factory=list)


class PilotCaseResponse(BaseModel):
    id: str
    project_id: str
    case_key: str
    import_session_id: str
    state: PilotState
    source_package_sha256: str
    source_files: list[PilotSourceFileEvidence]
    provenance: dict[str, Any]
    source_linkage_confidence: LinkageConfidence
    linkage_confidence: LinkageConfidence
    asset_references: list[str]
    asset_count: int
    metrics: PilotMetricEvidence
    data_quality: PilotDataQualitySnapshot
    created_by_user_id: str | None = None
    updated_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CreatePilotDecisionRequest(BaseModel):
    state: PilotState
    reason: str = Field(min_length=1, max_length=4000)


class PilotCaseDecisionResponse(BaseModel):
    id: str
    project_id: str
    pilot_case_id: str
    case_key: str
    sequence: int
    from_state: PilotState | None = None
    to_state: PilotState
    reason: str
    decided_by_user_id: str | None = None
    created_at: datetime


class PilotIntakeDataQualitySummary(BaseModel):
    schema_version: str
    project_id: str
    total_cases: int
    state_counts: dict[str, int]
    data_quality_status_counts: dict[str, int]
    linkage_confidence_counts: dict[str, int]
    source_linkage_confidence_counts: dict[str, int]
    source_file_count: int
    unique_source_hash_count: int
    exact_counts_case_count: int
    partial_counts_case_count: int
    rate_only_case_count: int
    no_metric_case_count: int
    multi_asset_case_count: int
    reported_impressions_total: int
    reported_clicks_total: int
    confirmed_mapping_count: int
    suggested_mapping_count: int
    rejected_mapping_count: int
    unmapped_mapping_count: int
    warning_issue_count: int
    blocking_issue_count: int
    non_exact_to_exact_promotion_count: int
    counts_reconstructed_from_rates: bool
    claim_boundary: dict[str, bool]
