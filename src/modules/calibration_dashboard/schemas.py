from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

EvidenceClass = Literal["real_client", "synthetic", "unclassified"]
EvidenceFilter = Literal["all", "real_client", "synthetic", "unclassified"]
InclusionStatus = Literal["included", "excluded", "deferred"]
WorkflowStatus = Literal["completed", "failed", "blocked", "cancelled"]


class UpsertCalibrationCaseRequest(BaseModel):
    evidence_class: EvidenceClass
    inclusion_status: InclusionStatus = "included"
    source_reference: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)


class CalibrationCaseResponse(BaseModel):
    id: str
    project_id: str
    case_id: str
    evidence_class: EvidenceClass
    inclusion_status: InclusionStatus
    source_reference: str | None = None
    notes: str | None = None
    updated_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateWorkflowMeasurementRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=255)
    stage: str = Field(min_length=1, max_length=120)
    status: WorkflowStatus = "completed"
    wall_clock_seconds: float = Field(ge=0)
    operator_touch_seconds: float = Field(ge=0)
    manual_action_count: int = Field(ge=0)
    report_version: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_touch_time(self):
        if self.operator_touch_seconds > self.wall_clock_seconds:
            raise ValueError("operator_touch_seconds cannot exceed wall_clock_seconds")
        return self


class WorkflowMeasurementResponse(BaseModel):
    id: str
    project_id: str
    case_id: str
    stage: str
    status: WorkflowStatus
    wall_clock_seconds: float
    operator_touch_seconds: float
    manual_action_count: int
    report_version: str | None = None
    notes: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime


class CalibrationMetric(BaseModel):
    key: str
    label: str
    domain: str
    unit: str
    value: float | int | None = None
    numerator: float | int | None = None
    denominator: float | int | None = None
    coverage: float | None = None
    evidence_status: Literal["available", "partial", "not_measured"]
    definition: str
    interpretation: str
    limitations: list[str] = Field(default_factory=list)


class CalibrationCaseRow(BaseModel):
    case_id: str
    campaign_id: str | None = None
    evidence_class: EvidenceClass
    inclusion_status: InclusionStatus
    system_finding_count: int
    resolved_finding_count: int
    unresolved_finding_count: int
    human_added_finding_count: int
    outcome_observation_count: int
    workflow_measurement_count: int
    operator_touch_seconds: float | None = None
    manual_action_count: int | None = None


class CalibrationDashboardResponse(BaseModel):
    schema_version: str
    generated_at: datetime
    project_id: str
    evidence_filter: EvidenceFilter
    metrics: list[CalibrationMetric]
    cases: list[CalibrationCaseRow]
    evidence_split: dict[str, dict[str, int]]
    review_status_counts: dict[str, int]
    workflow_status_counts: dict[str, int]
    claim_boundary: dict[str, bool]
    definitions_version: str
    source_fingerprints: dict[str, str | None] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class CalibrationExportManifest(BaseModel):
    schema_version: str
    project_id: str
    evidence_filter: EvidenceFilter
    generated_at: datetime
    payload_sha256: str
    claim_boundary: dict[str, bool]
    files: list[dict[str, Any]] = Field(default_factory=list)
