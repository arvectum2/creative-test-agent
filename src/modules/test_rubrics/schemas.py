from datetime import datetime

from pydantic import BaseModel, Field


class CriterionSchema(BaseModel):
    name: str
    description: str = ""


class CreateTestRubricRequest(BaseModel):
    name: str
    criteria: list[CriterionSchema] | None = None
    scale_min: int = 1
    scale_max: int = 10
    metadata: dict | None = None


class TestRubricResponse(BaseModel):
    id: str
    name: str
    criteria: list[CriterionSchema]
    scale_min: int
    scale_max: int
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
