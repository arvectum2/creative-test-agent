from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ReviewDecision = Literal[
    "supported",
    "partially_supported",
    "unsupported",
    "missed_by_system",
    "harmful_false_positive",
    "needs_rewording",
]
SeverityCorrectness = Literal["correct", "overstated", "understated", "not_applicable"]
SourceKind = Literal["system", "human"]
SubjectKind = Literal["authenticated_user", "declared_expert", "legacy"]
DisagreementStatus = Literal[
    "insufficient_reviews",
    "agreement",
    "disagreement",
    "adjudicated",
    "stale_adjudication",
]


class ReviewerIdentityInput(BaseModel):
    reviewer_subject_id: str | None = Field(default=None, min_length=1, max_length=255)
    reviewer_display_name: str | None = Field(default=None, min_length=1, max_length=255)


class CreateFindingReviewRequest(ReviewerIdentityInput):
    expected_system_finding_sha256: str = Field(min_length=64, max_length=64)
    reviewer_role: str = Field(min_length=1, max_length=160)
    decision: ReviewDecision
    correctness: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    traceability: int = Field(ge=1, le=5)
    severity_correctness: SeverityCorrectness
    reviewer_confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=4000)
    comment: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_system_decision(self):
        if self.decision == "missed_by_system":
            raise ValueError("missed_by_system must be recorded as a human finding")
        return self


class CreateHumanFindingRequest(ReviewerIdentityInput):
    campaign_id: str = Field(min_length=1, max_length=255)
    creative_record_id: str | None = Field(default=None, max_length=255)
    creative_asset_id: str | None = Field(default=None, max_length=255)
    criterion: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=4000)
    proposed_severity: Literal["info", "low", "medium", "high", "critical"] = "medium"
    reviewer_role: str = Field(min_length=1, max_length=160)
    relevance: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    traceability: int = Field(ge=1, le=5)
    reviewer_confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=4000)
    comment: str | None = Field(default=None, max_length=4000)


class CreateFindingAdjudicationRequest(BaseModel):
    expected_basis_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    adjudicator_subject_id: str | None = Field(default=None, min_length=1, max_length=255)
    adjudicator_display_name: str | None = Field(default=None, min_length=1, max_length=255)
    adjudicator_role: str = Field(min_length=1, max_length=160)
    decision: ReviewDecision
    correctness: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    traceability: int = Field(ge=1, le=5)
    severity_correctness: SeverityCorrectness
    adjudicator_confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=4000)
    comment: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_adjudication_decision(self):
        if self.decision == "missed_by_system":
            raise ValueError("missed_by_system is reserved for a separately recorded human finding")
        return self


class FindingReviewResponse(BaseModel):
    id: str
    project_id: str
    campaign_id: str | None = None
    case_id: str | None = None
    creative_record_id: str | None = None
    creative_asset_id: str | None = None
    test_run_id: str | None = None
    finding_id: str
    source_kind: SourceKind
    system_finding_snapshot: dict[str, Any] | None = None
    system_finding_snapshot_sha256: str | None = None
    human_finding_snapshot: dict[str, Any] | None = None
    human_finding_snapshot_sha256: str | None = None
    reviewer_user_id: str | None = None
    reviewer_subject_id: str
    reviewer_subject_kind: SubjectKind
    reviewer_display_name: str
    reviewer_role: str
    decision: ReviewDecision
    correctness: int
    relevance: int
    actionability: int
    traceability: int
    severity_correctness: SeverityCorrectness
    reviewer_confidence: float
    rationale: str
    comment: str | None = None
    revision_number: int
    reviewer_revision_number: int
    supersedes_review_id: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class FindingAdjudicationResponse(BaseModel):
    id: str
    project_id: str
    campaign_id: str | None = None
    case_id: str | None = None
    creative_record_id: str | None = None
    creative_asset_id: str | None = None
    test_run_id: str | None = None
    finding_id: str
    source_kind: SourceKind
    policy_id: str
    basis_review_ids: list[str]
    basis_fingerprint_sha256: str
    adjudicator_user_id: str | None = None
    adjudicator_subject_id: str
    adjudicator_subject_kind: SubjectKind
    adjudicator_display_name: str
    adjudicator_role: str
    decision: ReviewDecision
    correctness: int
    relevance: int
    actionability: int
    traceability: int
    severity_correctness: SeverityCorrectness
    adjudicator_confidence: float
    rationale: str
    comment: str | None = None
    adjudication_round: int
    supersedes_adjudication_id: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ReviewDisagreementResponse(BaseModel):
    project_id: str
    finding_id: str
    reviewer_count: int
    latest_reviews: list[FindingReviewResponse] = Field(default_factory=list)
    status: DisagreementStatus
    disagreement_reasons: list[str] = Field(default_factory=list)
    decision_values: list[str] = Field(default_factory=list)
    dimension_spreads: dict[str, int] = Field(default_factory=dict)
    severity_values: list[str] = Field(default_factory=list)
    basis_review_ids: list[str] = Field(default_factory=list)
    basis_fingerprint_sha256: str
    latest_adjudication: FindingAdjudicationResponse | None = None
    adjudication_current: bool = False


class ReviewableFindingResponse(BaseModel):
    finding_id: str
    project_id: str
    campaign_id: str
    case_id: str
    creative_record_id: str
    creative_asset_id: str | None = None
    test_run_id: str | None = None
    criterion: str
    text: str
    score: float | None = None
    confidence: float | None = None
    snapshot_sha256: str
    system_finding_snapshot: dict[str, Any]
    latest_review: FindingReviewResponse | None = None
    latest_reviews: list[FindingReviewResponse] = Field(default_factory=list)
    review_count: int = 0
    reviewer_count: int = 0
    current_snapshot_matches_latest_review: bool = True
    disagreement: ReviewDisagreementResponse | None = None


class ReviewableFindingDetailResponse(ReviewableFindingResponse):
    review_history: list[FindingReviewResponse] = Field(default_factory=list)
    adjudication_history: list[FindingAdjudicationResponse] = Field(default_factory=list)


class FindingReviewEvidenceExport(BaseModel):
    schema_version: str
    generated_at: datetime
    project_id: str
    review_count: int
    system_review_count: int
    human_finding_count: int
    adjudication_count: int
    reviews: list[FindingReviewResponse]
    adjudications: list[FindingAdjudicationResponse]
    disagreements: list[ReviewDisagreementResponse]
    claim_boundary: dict[str, bool]
