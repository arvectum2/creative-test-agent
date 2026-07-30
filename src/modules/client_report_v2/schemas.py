from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ExpertVerdict = Literal[
    "supported",
    "partially_supported",
    "unsupported",
    "needs_rewording",
    "not_reviewed",
]
ArtifactType = Literal[
    "html",
    "one_page_pptx",
    "full_pptx",
    "docx",
    "evidence",
    "xlsx",
    "manifest",
]


class ExpertAssessmentInput(BaseModel):
    finding_id: str = Field(min_length=1, max_length=240)
    verdict: ExpertVerdict
    rationale: str = Field(default="", max_length=2000)
    reviewer_role: str = Field(default="", max_length=160)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class GenerateClientReportV2Request(BaseModel):
    locale: Literal["ru", "en"] = "ru"
    expert_assessments: list[ExpertAssessmentInput] = Field(default_factory=list)
    force: bool = False

    @model_validator(mode="after")
    def unique_finding_ids(self):
        ids = [item.finding_id for item in self.expert_assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("expert_assessments must contain unique finding_id values")
        return self


class ClientReportV2Artifact(BaseModel):
    artifact_type: ArtifactType
    filename: str
    media_type: str
    sha256: str
    size_bytes: int


class ClientReportV2Response(BaseModel):
    report_id: str
    report_version: str
    project_id: str
    project_name: str
    locale: Literal["ru", "en"]
    input_fingerprint: str
    generated_at: datetime
    campaign_count: int
    finding_count: int
    reviewed_finding_count: int
    release_status: str
    artifacts: list[ClientReportV2Artifact]
    manifest_filename: str
    manifest_sha256: str
