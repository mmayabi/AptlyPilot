# file: app/models/job.py
from datetime import datetime
from enum import StrEnum
from typing import Optional
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB

# ------------------------------
# Enums
# ------------------------------
class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELED = "canceled"

class JobTriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"

class ScheduleType(StrEnum):
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

# ------------------------------
# Job Table
# ------------------------------
class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="job_templates.id")
    repo_id: int = Field(foreign_key="repos.id", index=True)
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    trigger_type: JobTriggerType = Field(default=JobTriggerType.MANUAL)
    triggered_by_user_id: int | None = Field(default=None, foreign_key="users.id")
    scheduled: bool = Field(default=False)

    # اصلاح: زمان اجرا یا schedule_type
    run_at: Optional[datetime] = Field(default=None, description="next job run (optional)")
    schedule_type: Optional[ScheduleType] = Field(default=ScheduleType.MANUAL)

    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# ------------------------------
# JobStep Table
# ------------------------------
class JobStep(SQLModel, table=True):
    """
    جدول JobStep: instance واقعی هر Step از یک Job که باید اجرا شود.
    نگهداری وضعیت step، ترتیب اجرا، پارامترهای واقعی و log اجرای step.
    """
    __tablename__ = "job_steps"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    step_template_id: int = Field(foreign_key="job_step_templates.id", index=True)
    script_id: int = Field(foreign_key="scripts.id")  # کپی script_id برای execution مستقل
    params: dict | None = Field(default_factory=dict, sa_column=Column(JSONB))  # مقادیر واقعی
    order: int = Field(default=0)  # ترتیب اجرای step
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)  # وضعیت step
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log: str | None = None