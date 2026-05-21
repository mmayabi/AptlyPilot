from datetime import datetime
from sqlmodel import Field, SQLModel, Column
from sqlalchemy.dialects.postgresql import JSONB  # برای PostgreSQL

class JobTemplate(SQLModel, table=True):
    __tablename__ = "job_templates"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, unique=True)
    description: str | None = None
    steps: list[dict] = Field(default_factory=list, sa_column=Column(JSONB))  # ✅ JSONB برای PostgreSQL
    created_by: int | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)