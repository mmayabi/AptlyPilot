# file: app/schemas/job_schedule.py

from datetime import datetime

from pydantic import BaseModel

from app.models.job_schedule import JobScheduleStatus, JobScheduleType


class JobScheduleCreate(BaseModel):
    job_id: int
    schedule_type: JobScheduleType
    next_run_at: datetime


class JobScheduleUpdate(BaseModel):
    schedule_type: JobScheduleType | None = None
    status: JobScheduleStatus | None = None
    next_run_at: datetime | None = None


class JobScheduleRead(BaseModel):
    id: int
    job_id: int
    schedule_type: JobScheduleType
    status: JobScheduleStatus
    next_run_at: datetime
    last_run_at: datetime | None = None
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime