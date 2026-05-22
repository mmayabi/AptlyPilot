from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.job import JobStatus, JobTriggerType, ScheduleType


class JobStepRead(BaseModel):
    id: int
    script_id: int
    order: int
    params: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log: str | None = None


class JobCreate(BaseModel):
    template_id: int
    repo_id: int
    trigger_type: JobTriggerType = JobTriggerType.MANUAL
    run_at: datetime | None = None
    schedule_type: ScheduleType = ScheduleType.MANUAL
    params: list[dict[str, Any]] = Field(default_factory=list)


class JobUpdate(BaseModel):
    trigger_type: JobTriggerType | None = None
    run_at: datetime | None = None
    schedule_type: ScheduleType | None = None


class JobRead(BaseModel):
    id: int
    template_id: int
    repo_id: int
    status: JobStatus
    trigger_type: JobTriggerType
    scheduled: bool
    run_at: datetime | None = None
    schedule_type: ScheduleType
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    steps: list[JobStepRead] = Field(default_factory=list)