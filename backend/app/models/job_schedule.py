# file: app/models/job_schedule.py

from datetime import datetime
from enum import StrEnum

from sqlmodel import SQLModel, Field


class JobScheduleType(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class JobScheduleStatus(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class JobSchedule(SQLModel, table=True):
    """
    جدول JobSchedule:
    تعریف زمان‌بندی اجرای یک Job.
    Scheduler براساس این جدول، اجرای job را وارد WorkerQueue می‌کند.
    """
    __tablename__ = "job_schedules"

    id: int | None = Field(default=None, primary_key=True)

    job_id: int = Field(foreign_key="jobs.id", index=True)

    schedule_type: JobScheduleType = Field(index=True)
    status: JobScheduleStatus = Field(
        default=JobScheduleStatus.ENABLED,
        index=True,
    )

    next_run_at: datetime = Field(index=True)
    last_run_at: datetime | None = None

    created_by_user_id: int | None = Field(default=None, foreign_key="users.id")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)