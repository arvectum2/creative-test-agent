from datetime import datetime

from pydantic import BaseModel, Field


class CreateCreativeAssetRequest(BaseModel):
    title: str
    asset_type: str
    text_content: str | None = None
    file_path: str | None = None
    project_id: str | None = None
    metadata: dict = Field(default_factory=dict)
class CreateVersionRequest(BaseModel):
    version_label: str | None = None
    revision_summary: str | None = None
    revision_source: str = "manual_revision"
    title: str | None = None
    text_content: str | None = None
    metadata: dict | None = None


class CreativeAssetResponse(BaseModel):
    id: str
    title: str
    asset_type: str
    text_content: str | None = None
    extracted_text: str | None = None
    original_filename: str | None = None
    file_path: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    project_id: str | None = None
    metadata: dict
    created_at: datetime
    parent_asset_id: str | None = None
    version_label: str | None = None
    version_number: int | None = None
    revision_summary: str | None = None
    revision_source: str | None = None


class VersionedAssetResponse(CreativeAssetResponse):
    children: list[CreativeAssetResponse] = Field(default_factory=list)
class VersionChainResponse(BaseModel):
    root: CreativeAssetResponse | None = None
    versions: list[CreativeAssetResponse]
