from datetime import datetime
from pydantic import BaseModel
from app.models.job import JobAction, JobStatus, JobTriggerType
from app.models.job_step import JobStep

class JobStepRead(BaseModel):
    id: int
    job_id: int
    name: str
    type: str
    command: str | None
    action: str | None
    params: dict | None
    status: JobStatus
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class JobRead(BaseModel):
    id: int
    repo_id: int
    action: JobAction
    status: JobStatus
    trigger_type: JobTriggerType
    triggered_by_user_id: int | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    steps: list[JobStepRead] | None = None  # لیست Stepهای Job

    class Config:
        orm_mode = True


class JobCreateRequest(BaseModel):
    repo_id: int
    steps: list[dict]  # هر Step شامل name, type, command/action, params
    trigger_type: JobTriggerType = JobTriggerType.MANUAL