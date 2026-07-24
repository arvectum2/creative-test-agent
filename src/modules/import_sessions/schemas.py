from datetime import datetime

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
