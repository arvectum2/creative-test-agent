from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MappingFieldResponse(BaseModel):
    key: str
    label: str
    description: str
    expected_types: list[str] = Field(default_factory=list)


class MappingSuggestionResponse(BaseModel):
    id: str
    mapping_run_id: str
    source_column_id: str
    target_field: str
    rank: int
    confidence: float
    method: str
    explanation: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class ColumnMappingResponse(BaseModel):
    id: str
    source_table_id: str
    source_column_id: str
    position: int
    source_header: str | None = None
    normalized_header: str
    inferred_type: str
    is_empty: bool
    sample_values: list = Field(default_factory=list)
    target_field: str | None = None
    status: str
    confidence: float | None = None
    decision_source: str
    selected_suggestion_id: str | None = None
    mapping_profile_id: str | None = None
    rationale: dict = Field(default_factory=dict)
    decided_by_user_id: str | None = None
    suggestions: list[MappingSuggestionResponse] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MappingRunResponse(BaseModel):
    id: str
    source_table_id: str
    source_file_id: str
    import_session_id: str
    project_id: str
    run_number: int
    engine_name: str
    engine_version: str
    mapping_profile_id: str | None = None
    status: str
    suggestion_count: int
    warnings: list[dict] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime | None = None


class TableMappingResponse(BaseModel):
    run: MappingRunResponse | None = None
    source_table_id: str
    mapped_columns: int
    confirmed_columns: int
    suggested_columns: int
    rejected_columns: int
    unmapped_columns: int
    warnings: list[dict] = Field(default_factory=list)
    columns: list[ColumnMappingResponse] = Field(default_factory=list)


class GenerateMappingRequest(BaseModel):
    mapping_profile_id: str | None = None
    force: bool = False


class ColumnMappingDecisionRequest(BaseModel):
    status: Literal["confirmed", "rejected", "unmapped"]
    target_field: str | None = None
    selected_suggestion_id: str | None = None
    rationale: dict = Field(default_factory=dict)
    allow_duplicate: bool = False


class CreateMappingProfileRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=255)
    source_table_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    source_label: str | None = Field(default=None, max_length=255)
    sheet_name_pattern: str | None = Field(default=None, max_length=255)


class MappingProfileRuleResponse(BaseModel):
    id: str
    mapping_profile_id: str
    source_key: str
    source_header: str | None = None
    source_inferred_type: str | None = None
    target_field: str
    confidence: float
    created_from_column_id: str | None = None
    is_active: bool = True
    created_at: datetime | None = None


class MappingProfileResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None = None
    source_label: str | None = None
    file_format: str | None = None
    sheet_name_pattern: str | None = None
    version: int
    status: str
    created_from_table_id: str
    created_by_user_id: str | None = None
    rules: list[MappingProfileRuleResponse] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApplyMappingProfileRequest(BaseModel):
    mapping_profile_id: str = Field(min_length=1, max_length=255)
    force: bool = True
