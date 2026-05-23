from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.job import JobDefinitionStatus


class JobStepRead(BaseModel):
    id: int
    script_id: int
    order: int
    params: dict[str, Any] = Field(default_factory=dict)

class JobCreate(BaseModel):
    template_id: int
    repo_id: int
    params: list[dict[str, Any]] = Field(default_factory=list)

class JobUpdate(BaseModel):
    status: JobDefinitionStatus | None = None

class JobRead(BaseModel):
    id: int
    template_id: int
    repo_id: int
    status: JobDefinitionStatus
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime
    steps: list[JobStepRead] = Field(default_factory=list)