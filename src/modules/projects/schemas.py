from datetime import datetime

from pydantic import BaseModel, Field

from .models import ProjectStatus


class CreateProjectRequest(BaseModel):
    client_id: str
    name: str
    description: str | None = None
    status: ProjectStatus = ProjectStatus.draft


class ProjectResponse(BaseModel):
    id: str
    client_id: str
    name: str
    description: str | None = None
    status: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None
