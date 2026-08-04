from datetime import datetime

from pydantic import BaseModel, Field

from .models import ExportStatus, ExportType


class ExportJobResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    export_type: str
    status: str
    file_path: str | None = None
    error_message: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    completed_at: datetime | None = None
