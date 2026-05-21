from datetime import datetime
from enum import StrEnum
from sqlmodel import Field, SQLModel

class JobAction(StrEnum):
    MIRROR_UPDATE = "mirror_update"
    SNAPSHOT_CREATE = "snapshot_create"
    PUBLISH_SWITCH = "publish_switch"
    CLEANUP = "cleanup"
    FULL_SYNC = "full_sync"

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

class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: int | None = Field(default=None, primary_key=True)
    repo_id: int = Field(foreign_key="repos.id", index=True)
    action: JobAction = Field(index=True)
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    trigger_type: JobTriggerType = Field(default=JobTriggerType.MANUAL)
    triggered_by_user_id: int | None = Field(default=None, foreign_key="users.id")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # ستونهای زمان‌بندی اضافه شدند
    scheduled: bool = Field(default=False)
    run_at: datetime | None = None  # زمان اجرای بعدی