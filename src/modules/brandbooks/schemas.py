from datetime import datetime

from pydantic import BaseModel, Field

from .models import BrandbookDocumentType


class BrandbookDocumentResponse(BaseModel):
    id: str
    client_id: str | None = None
    project_id: str | None = None
    brand_profile_id: str | None = None
    title: str
    document_type: str
    text_content: str | None = None
    extracted_text: str | None = None
    file_path: str | None = None
    analysis: dict | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None


class BrandbookContextResult(BaseModel):
    snippets: list[str] = Field(default_factory=list)
    total_chars: int = 0
