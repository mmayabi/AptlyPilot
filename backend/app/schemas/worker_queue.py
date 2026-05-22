# file: app/schemas/worker_queue.py

from datetime import datetime

from pydantic import BaseModel

from app.models.worker_queue import WorkerQueueStatus, WorkerQueueRequestedBy


class WorkerQueueRead(BaseModel):
    id: int
    job_id: int
    job_step_id: int
    schedule_id: int | None = None
    execution_id: str

    status: WorkerQueueStatus
    requested_by: WorkerQueueRequestedBy
    requested_by_user_id: int | None = None

    run_after: datetime | None = None

    attempt_count: int
    max_attempts: int

    locked_by: str | None = None
    locked_at: datetime | None = None
    heartbeat_at: datetime | None = None

    started_at: datetime | None = None
    finished_at: datetime | None = None

    timeout_seconds: int
    error_message: str | None = None

    created_at: datetime
    updated_at: datetime


class WorkerRunOnceResponse(BaseModel):
    executed: bool
    message: str
    queue_item: WorkerQueueRead | None = None