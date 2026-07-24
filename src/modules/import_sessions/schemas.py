from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateImportSessionRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    notes: str | None = None
    metadata: dict = Field(default_factory=dict)


class ImportSessionResponse(BaseModel):
    id: str
    project_id: str
    name: str
    notes: str | None = None
    status: str
    created_by_user_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    file_count: int = 0
    total_bytes: int = 0
    created_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None


class ImportSourceFileResponse(BaseModel):
    id: str
    import_session_id: str
    project_id: str
    original_filename: str
    extension: str | None = None
    declared_mime_type: str | None = None
    file_size_bytes: int
    sha256: str
    uploaded_by_user_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class ImportFileIntegrityResponse(BaseModel):
    file_id: str
    sha256: str
    exists: bool
    checksum_match: bool


class ImportIntegrityReportResponse(BaseModel):
    import_session_id: str
    ok: bool
    checked_files: int
    missing_files: list[str] = Field(default_factory=list)
    corrupted_files: list[str] = Field(default_factory=list)
    files: list[ImportFileIntegrityResponse] = Field(default_factory=list)


class SourceInspectionResponse(BaseModel):
    id: str
    source_file_id: str
    import_session_id: str
    project_id: str
    inspection_number: int
    status: str
    parser_name: str
    parser_version: str
    file_format: str | None = None
    encoding: str | None = None
    delimiter: str | None = None
    table_count: int = 0
    row_count: int = 0
    column_count: int = 0
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None


class SourceColumnResponse(BaseModel):
    id: str
    source_table_id: str
    position: int
    source_header: str | None = None
    normalized_header: str
    inferred_type: str
    is_empty: bool
    duplicate_index: int = 1
    duplicate_group: str | None = None
    non_empty_count: int = 0
    sample_values: list[Any] = Field(default_factory=list)


class SourceRowResponse(BaseModel):
    id: str
    source_table_id: str
    source_row_number: int
    row_kind: str
    values: list[Any] = Field(default_factory=list)
    cell_types: list[str] = Field(default_factory=list)


class SourceTableSummaryResponse(BaseModel):
    id: str
    inspection_id: str
    source_file_id: str
    sheet_index: int
    sheet_name: str
    header_row_number: int | None = None
    header_confidence: float | None = None
    source_row_count: int = 0
    data_row_count: int = 0
    column_count: int = 0
    truncated: bool = False
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class SourceTableDetailResponse(SourceTableSummaryResponse):
    columns: list[SourceColumnResponse] = Field(default_factory=list)
    preview_rows: list[SourceRowResponse] = Field(default_factory=list)


class SourceRowPageResponse(BaseModel):
    source_table_id: str
    offset: int
    limit: int
    total: int
    rows: list[SourceRowResponse] = Field(default_factory=list)
