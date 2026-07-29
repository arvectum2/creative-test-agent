from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EvidenceBoundary(BaseModel):
    causal_interpretation_allowed: bool = False
    numeric_uplift_prediction_generated: bool = False
    individual_asset_outcome_attribution_allowed: bool = False
    missing_values_inferred: bool = False
    diagnostics_are_model_outputs_not_factual_outcomes: bool = True


class EvidenceLimitation(BaseModel):
    code: str
    message: str
    severity: str = "warning"
    context: dict[str, Any] = Field(default_factory=dict)


class AgentDiagnosticEvidence(BaseModel):
    test_run_id: str | None = None
    status: str = "missing"
    summary: str = ""
    overall_score: float | None = None
    proposed_recommendation: str = ""
    effective_recommendation: str = ""
    findings: list[dict[str, Any]] = Field(default_factory=list)
    scorecard: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    visual_traceability_status: str = "not_available"
    visual_decision_status: str = "not_available"
    completed_at: datetime | None = None


class CampaignAssetEvidence(BaseModel):
    creative_record_id: str
    creative_asset_id: str | None = None
    title: str
    filename: str | None = None
    preview_url: str | None = None
    brand: str | None = None
    inferred_platform: str | None = None
    linkage_status: str
    linkage_confidence: float
    linkage_notes: list[str] = Field(default_factory=list)
    accepted_for_campaign_set: bool
    diagnostic: AgentDiagnosticEvidence


class CampaignOutcomeEvidence(BaseModel):
    observation_id: str
    metric: str
    metric_label: str
    control_n: int | None = None
    test_n: int | None = None
    cg_rate: float | None = None
    tg_rate: float | None = None
    uplift_pp_descriptive: float | None = None
    evidence_status: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    platform: str | None = None
    source_sheet: str | None = None
    source_row_number: int | None = None
    causal_interpretation_allowed: bool = False
    numeric_prediction_generated: bool = False
    notes: list[str] = Field(default_factory=list)


class CampaignEvidence(BaseModel):
    campaign_id: str
    case_id: str
    brand: str | None = None
    product: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    platform: str | None = None
    is_contrast_case: bool = False
    showcase_rank: int | None = None
    campaign_level_outcomes: bool = True
    individual_asset_attribution_allowed: bool = False
    assets: list[CampaignAssetEvidence] = Field(default_factory=list)
    outcomes: list[CampaignOutcomeEvidence] = Field(default_factory=list)
    limitations: list[EvidenceLimitation] = Field(default_factory=list)


class CampaignEvidenceSummary(BaseModel):
    campaign_count: int
    outcome_count: int
    creative_count: int
    accepted_asset_count: int
    rejected_asset_count: int
    unlabelled_asset_count: int
    campaigns_with_diagnostics: int
    campaigns_with_limitations: int


class CampaignEvidenceWorkspace(BaseModel):
    project_id: str
    project_name: str
    normalization_run_id: str
    source_fingerprint: str | None = None
    mapping_version: str | None = None
    generated_from_loader: str
    evidence_boundaries: EvidenceBoundary
    summary: CampaignEvidenceSummary
    campaigns: list[CampaignEvidence]
    unlabelled_assets: list[CampaignAssetEvidence] = Field(default_factory=list)
