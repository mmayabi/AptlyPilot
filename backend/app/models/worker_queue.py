# file: app/models/worker_queue.py

from datetime import datetime
from enum import StrEnum

from sqlmodel import SQLModel, Field


class WorkerQueueStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"
    SKIPPED = "skipped"


class WorkerQueueRequestedBy(StrEnum):
    MANUAL = "manual"
    SCHEDULER = "scheduler"
    RETRY = "retry"
    SYSTEM = "system"


class WorkerQueueItem(SQLModel, table=True):
    """
    صف اجرای Worker.
    هر رکورد نشان‌دهنده درخواست اجرای یک JobStep است.
    execution_id همه stepهای یک اجرای کامل job را به هم وصل می‌کند.
    """
    __tablename__ = "worker_queue"

    id: int | None = Field(default=None, primary_key=True)

    job_id: int = Field(foreign_key="jobs.id", index=True)
    job_step_id: int = Field(foreign_key="job_steps.id", index=True)
    schedule_id: int | None = Field(default=None, foreign_key="job_schedules.id", index=True)

    execution_id: str = Field(index=True)

    status: WorkerQueueStatus = Field(default=WorkerQueueStatus.QUEUED, index=True)

    requested_by: WorkerQueueRequestedBy = Field(
        default=WorkerQueueRequestedBy.MANUAL,
        index=True,
    )
    requested_by_user_id: int | None = Field(default=None, foreign_key="users.id")

    run_after: datetime | None = Field(default=None, index=True)

    attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=1)

    locked_by: str | None = Field(default=None, index=True)
    locked_at: datetime | None = None
    heartbeat_at: datetime | None = None

    started_at: datetime | None = None
    finished_at: datetime | None = None

    timeout_seconds: int = Field(default=3600)
    log: str | None = None
    error_message: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)