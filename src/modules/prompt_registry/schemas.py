from datetime import datetime

from pydantic import BaseModel, Field


class PromptVersionResponse(BaseModel):
    id: str
    stage_name: str
    version: str
    template_path: str
    template_hash: str
    is_active: bool
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
