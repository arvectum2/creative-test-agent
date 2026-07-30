from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.modules.campaign_evidence.schemas import (
    CampaignAssetEvidence,
    CampaignEvidence,
    EvidenceBoundary,
)

DemoStepStatus = Literal["ready", "limited", "blocked"]


class DemoVisualObservation(BaseModel):
    observation_path: str
    label: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_reference_ids: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)


class DemoVisualExtraction(BaseModel):
    status: str = "missing"
    provider: str = ""
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    completeness_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    fingerprint: str = ""
    reference_ids: list[str] = Field(default_factory=list)
    observations: list[DemoVisualObservation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DemoPrimaryAsset(BaseModel):
    asset: CampaignAssetEvidence
    visual_extraction: DemoVisualExtraction


class DemoStep(BaseModel):
    ordinal: int = Field(ge=1, le=7)
    code: str
    title: str
    operator_prompt: str
    status: DemoStepStatus
    evidence_references: list[str] = Field(default_factory=list)
    limitation_codes: list[str] = Field(default_factory=list)


class DemoCampaignOption(BaseModel):
    campaign_id: str
    case_id: str
    label: str
    showcase_rank: int | None = None
    status: DemoStepStatus
    reason: str


class DemoReportArtifact(BaseModel):
    artifact_type: str
    filename: str
    media_type: str
    sha256: str
    size_bytes: int


class DemoReportState(BaseModel):
    report_id: str
    report_version: str
    release_status: str
    generated_at: str
    manifest_sha256: str
    artifacts: list[DemoReportArtifact] = Field(default_factory=list)


class OzonClientDemoState(BaseModel):
    schema_name: Literal["ozon_e2e_client_demo"] = "ozon_e2e_client_demo"
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    project_name: str
    selected_campaign_id: str
    selected_case_id: str
    campaign_options: list[DemoCampaignOption]
    selected_campaign: CampaignEvidence
    primary_asset: DemoPrimaryAsset | None = None
    steps: list[DemoStep]
    report: DemoReportState | None = None
    demo_ready: bool
    evidence_boundaries: EvidenceBoundary
    operator_stop_conditions: list[str] = Field(default_factory=list)
