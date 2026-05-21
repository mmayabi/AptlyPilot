from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class RepoStatus(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    FAILED = "failed"
    RUNNING = "running"
    DISABLED = "disabled"


class Repo(SQLModel, table=True):
    __tablename__ = "repos"

    id: int | None = Field(default=None, primary_key=True)

    name: str = Field(index=True, unique=True, nullable=False)
    mirror_name: str = Field(index=True, nullable=False)

    enabled: bool = Field(default=True)

    url: str
    distribution: str

    components: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    architectures: list[str] = Field(default_factory=list, sa_column=Column(JSONB))

    raw_config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))

    status: RepoStatus = Field(default=RepoStatus.UNKNOWN)
    last_sync_status: str | None = None
    last_sync_at: datetime | None = None
    last_error: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)