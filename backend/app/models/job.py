# file: app/models/job.py
from datetime import datetime
from enum import StrEnum
from typing import Optional
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB

#Job = تعریف یک کار قابل اجرا
#JobStep = تعریف stepهای آن کار
#JobSchedule = تعریف زمان‌بندی
#WorkerQueue = صف اجرا + تاریخچه اجرای واقعی step

# ------------------------------
# Enums
# ------------------------------
class JobDefinitionStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"

# ------------------------------
# Job Table
# ------------------------------
class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="job_templates.id")
    repo_id: int = Field(foreign_key="repos.id", index=True)

    status: JobDefinitionStatus = Field(default=JobDefinitionStatus.ACTIVE, index=True)

    created_by_user_id: int | None = Field(default=None, foreign_key="users.id")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
# ------------------------------
# JobStep Table
# ------------------------------
class JobStep(SQLModel, table=True):
    __tablename__ = "job_steps"

    id: int | None = Field(default=None, primary_key=True)

    job_id: int = Field(foreign_key="jobs.id", index=True)
    step_template_id: int = Field(foreign_key="job_step_templates.id", index=True)
    script_id: int = Field(foreign_key="scripts.id")

    params: dict | None = Field(default_factory=dict, sa_column=Column(JSONB))
    order: int = Field(default=0)