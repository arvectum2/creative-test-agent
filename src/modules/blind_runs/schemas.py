from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FreezeDiagnosticRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str = Field(min_length=1, max_length=255)
    diagnostic_output: dict[str, Any]
    prompt_version_ids: list[str] = Field(min_length=1, max_length=100)
    model_profile_id: str = Field(min_length=1, max_length=255)
    code_revision: str = Field(min_length=40, max_length=64)
    execution_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("execution_id", "model_profile_id")
    @classmethod
    def strip_identifier(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("identifier cannot be blank")
        return stripped

    @field_validator("prompt_version_ids")
    @classmethod
    def validate_prompt_version_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("prompt version identifiers cannot be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("prompt version identifiers must be unique")
        return normalized

    @field_validator("code_revision")
    @classmethod
    def validate_code_revision(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) not in {40, 64}:
            raise ValueError("code_revision must be a 40- or 64-character hexadecimal hash")
        if any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError("code_revision must be hexadecimal")
        return normalized


class PromptVersionSnapshot(BaseModel):
    id: str
    stage_name: str
    version: str
    template_path: str
    template_hash: str
    metadata: Any = None


class ModelProfileSnapshot(BaseModel):
    id: str
    profile_name: str
    provider: str
    model: str
    base_url: str | None = None
    enabled: bool
    default_for_demo: bool
    timeout_seconds: int
    metadata: Any = None


class BlindDiagnosticRevisionResponse(BaseModel):
    id: str
    project_id: str
    pilot_case_id: str
    case_key: str
    revision_number: int
    execution_id: str
    supersedes_revision_id: str | None = None
    previous_revision_sha256: str | None = None

    diagnostic_output: dict[str, Any]
    diagnostic_output_sha256: str
    input_provenance: dict[str, Any]
    input_provenance_sha256: str
    prompt_manifest: list[PromptVersionSnapshot]
    prompt_manifest_sha256: str
    model_profile: ModelProfileSnapshot
    model_profile_sha256: str
    code_revision: str
    execution_metadata: dict[str, Any]
    execution_metadata_sha256: str
    revision_manifest: dict[str, Any]
    revision_sha256: str

    created_by_user_id: str | None = None
    frozen_at: datetime
    created_at: datetime


class RecordOutcomeEnvelopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome_schema_version: str = Field(min_length=1, max_length=120)
    outcome_payload: dict[str, Any]
    provenance: dict[str, Any] = Field(default_factory=dict)


class OutcomeEnvelopeMetadataResponse(BaseModel):
    id: str
    project_id: str
    pilot_case_id: str
    case_key: str
    outcome_schema_version: str
    outcome_payload_sha256: str
    provenance_sha256: str
    created_by_user_id: str | None = None
    sealed_at: datetime
    created_at: datetime


class RevealedOutcomeEnvelopeResponse(OutcomeEnvelopeMetadataResponse):
    outcome_payload: dict[str, Any]
    provenance: dict[str, Any]
