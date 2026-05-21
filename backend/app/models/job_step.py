from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.models.job import JobStatus

class JobStep(SQLModel, table=True):
    __tablename__ = "job_steps"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    name: str = Field(index=True)
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)

    # دو حالت برای Step
    type: str = Field(default="api")  # "command" یا "api"
    command: str | None = None            # برای type="command"
    action: str | None = None             # برای type="api"
    params: dict | None = Field(default_factory=dict, sa_column=Column(JSONB))  # برای type="api"

    started_at: datetime | None = None
    finished_at: datetime | None = None
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)