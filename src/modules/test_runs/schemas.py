from datetime import datetime

from pydantic import BaseModel, Field


class CreateTestRunRequest(BaseModel):
    creative_asset_id: str
    brand_profile_id: str | None = None
    audience_profile_ids: list[str] = Field(default_factory=list)
    rubric_id: str | None = None
    input_context: dict = Field(default_factory=dict)
    project_id: str | None = None


class VisualConfidenceFields(BaseModel):
    visual_confidence_score: float | None = None
    visual_confidence_band: str = "not_applicable"
    visual_abstention_status: str = "not_applicable"
    visual_abstention_reasons: list[str] = Field(default_factory=list)
    visual_assessment_allowed: bool = True
    visual_client_release_allowed: bool = True


class FindingItem(VisualConfidenceFields):
    criterion: str
    score: float
    explanation: str
    confidence: float = 1.0
    evidence_notes: list[str] = Field(default_factory=list)
    visual_evidence_refs: list[str] = Field(default_factory=list)
    rejected_visual_evidence_refs: list[str] = Field(default_factory=list)
    visual_traceability_status: str = "not_used"
    traceability_notes: list[str] = Field(default_factory=list)


class ScorecardEntry(VisualConfidenceFields):
    criterion: str
    score: float
    rationale: str = ""
    recommendation: str = ""
    confidence: float = 1.0
    evidence_notes: list[str] = Field(default_factory=list)
    visual_evidence_fingerprint: str = ""
    evidence_scope: str = "non_visual"
    visual_evidence_refs: list[str] = Field(default_factory=list)
    rejected_visual_evidence_refs: list[str] = Field(default_factory=list)
    visual_traceability_status: str = "not_used"
    traceability_notes: list[str] = Field(default_factory=list)


class RiskEntry(VisualConfidenceFields):
    risk_type: str = ""
    level: str = ""
    description: str = ""
    mitigation: str = ""
    confidence: float = 1.0
    provenance: list[dict] = Field(default_factory=list)
    visual_evidence_fingerprint: str = ""
    evidence_scope: str = "non_visual"
    visual_evidence_refs: list[str] = Field(default_factory=list)
    rejected_visual_evidence_refs: list[str] = Field(default_factory=list)
    visual_traceability_status: str = "not_used"
    traceability_notes: list[str] = Field(default_factory=list)


class AudienceReaction(VisualConfidenceFields):
    audience_profile_id: str = ""
    segment_name: str = ""
    reaction: str = ""
    positive_triggers: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    engagement_probability: float = 0.0
    confidence: float = 1.0
    visual_evidence_status: str = "not_applicable"
    visual_evidence_fingerprint: str = ""
    evidence_scope: str = "non_visual"
    visual_evidence_refs: list[str] = Field(default_factory=list)
    rejected_visual_evidence_refs: list[str] = Field(default_factory=list)
    visual_traceability_status: str = "not_used"
    traceability_notes: list[str] = Field(default_factory=list)


class ComplianceViolation(VisualConfidenceFields):
    rule: str = ""
    severity: str = ""
    details: str = ""
    evidence_scope: str = "non_visual"
    visual_evidence_refs: list[str] = Field(default_factory=list)
    rejected_visual_evidence_refs: list[str] = Field(default_factory=list)
    visual_traceability_status: str = "not_used"
    traceability_notes: list[str] = Field(default_factory=list)


class BrandbookCompliance(VisualConfidenceFields):
    overall_verdict: str = "compliant"
    violations: list[ComplianceViolation] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    compliance_score: float = 10.0
    confidence: float = 1.0
    visual_evidence_fingerprint: str = ""
    visual_evidence_refs: list[str] = Field(default_factory=list)
    rejected_visual_evidence_refs: list[str] = Field(default_factory=list)
    visual_traceability_status: str = "not_used"
    traceability_notes: list[str] = Field(default_factory=list)


class TestRunResponse(BaseModel):
    id: str
    creative_asset_id: str
    brand_profile_id: str | None = None
    audience_profile_ids: list[str]
    rubric_id: str | None = None
    status: str
    input_context: dict
    project_id: str | None = None
    findings: list[FindingItem]
    summary: str = ""
    summary_details: dict = Field(default_factory=dict)
    overall_score: float = 0.0
    scorecard: list[ScorecardEntry] = Field(default_factory=list)
    risks: list[RiskEntry] = Field(default_factory=list)
    audience_reactions: list[AudienceReaction] = Field(default_factory=list)
    brandbook_compliance: BrandbookCompliance = Field(default_factory=BrandbookCompliance)
    final_recommendation: str = ""
    effective_recommendation: str = ""
    final_recommendation_confidence: float = 1.0
    final_recommendation_rationale: str = ""
    final_recommendation_actions: list[str] = Field(default_factory=list)
    final_recommendation_visual_evidence_refs: list[str] = Field(default_factory=list)
    final_recommendation_visual_traceability_status: str = "not_used"
    visual_context: dict | None = None
    visual_evidence: dict | None = None
    visual_evidence_trace: dict | None = None
    visual_traceability_status: str = "not_applicable"
    unresolved_visual_finding_count: int = 0
    visual_confidence_policy: dict | None = None
    visual_decision_status: str = "not_applicable"
    visual_abstention_count: int = 0
    visual_review_required_count: int = 0
    created_at: datetime
    completed_at: datetime | None = None
