from datetime import datetime

from pydantic import BaseModel, Field

from .models import KnowledgeSourceType


class CreateKnowledgeItemRequest(BaseModel):
    source_type: KnowledgeSourceType = KnowledgeSourceType.other
    source_id: str | None = None
    client_id: str | None = None
    project_id: str | None = None
    title: str
    content: str | None = None
    tags: list[str] = Field(default_factory=list)
class KnowledgeItemResponse(BaseModel):
    id: str
    source_type: str
    source_id: str | None = None
    client_id: str | None = None
    project_id: str | None = None
    title: str
    content: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None


class KnowledgeSearchResult(BaseModel):
    item: KnowledgeItemResponse
    score: float
    matched_terms: list[str] = Field(default_factory=list)