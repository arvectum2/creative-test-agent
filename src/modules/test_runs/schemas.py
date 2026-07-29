from datetime import datetime

from pydantic import BaseModel, Field


class CreateTestRunRequest(BaseModel):
    creative_asset_id: str
    brand_profile_id: str | None = None
    audience_profile_ids: list[str] = Field(default_factory=list)
    rubric_id: str | None = None
    input_context: dict = Field(default_factory=dict)
    project_id: str | None = None


class FindingItem(BaseModel):
    criterion: str
    score: float
    explanation: str
    confidence: float = 1.0
    evidence_notes: list[str] = Field(default_factory=list)


class ScorecardEntry(BaseModel):
    criterion: str
    score: float
    rationale: str = ""
    recommendation: str = ""
    confidence: float = 1.0
    evidence_notes: list[str] = Field(default_factory=list)
    visual_evidence_fingerprint: str = ""


class RiskEntry(BaseModel):
    risk_type: str = ""
    level: str = ""
    description: str = ""
    mitigation: str = ""
    confidence: float = 1.0
    provenance: list[dict] = Field(default_factory=list)
    visual_evidence_fingerprint: str = ""


class AudienceReaction(BaseModel):
    audience_profile_id: str = ""
    segment_name: str = ""
    reaction: str = ""
    positive_triggers: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    engagement_probability: float = 0.0
    confidence: float = 1.0
    visual_evidence_status: str = "not_applicable"
    visual_evidence_fingerprint: str = ""


class ComplianceViolation(BaseModel):
    rule: str = ""
    severity: str = ""
    details: str = ""


class BrandbookCompliance(BaseModel):
    overall_verdict: str = "compliant"
    violations: list[ComplianceViolation] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    compliance_score: float = 10.0
    confidence: float = 1.0
    visual_evidence_fingerprint: str = ""


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
    overall_score: float = 0.0
    scorecard: list[ScorecardEntry] = Field(default_factory=list)
    risks: list[RiskEntry] = Field(default_factory=list)
    audience_reactions: list[AudienceReaction] = Field(default_factory=list)
    brandbook_compliance: BrandbookCompliance = Field(default_factory=BrandbookCompliance)
    final_recommendation: str = ""
    final_recommendation_confidence: float = 1.0
    final_recommendation_rationale: str = ""
    final_recommendation_actions: list[str] = Field(default_factory=list)
    visual_context: dict | None = None
    visual_evidence: dict | None = None
    created_at: datetime
    completed_at: datetime | None = None
