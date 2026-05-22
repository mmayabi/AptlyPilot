from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB


class Script(SQLModel, table=True):
    """
    جدول Script: تعریف scriptهای قابل اجرا توسط Worker.
    شامل نام فایل script، پارامترهای مورد نیاز، timeout و سیاست retry.
    """
    __tablename__ = "scripts"

    id: int | None = Field(default=None, primary_key=True)

    name: str = Field(index=True, unique=True)
    description: str | None = None

    params: dict | None = Field(default_factory=dict, sa_column=Column(JSONB))

    timeout_seconds: int = Field(default=3600)
    max_retries: int = Field(default=0)
    retry_delay_seconds: int = Field(default=300)

    retry_on_timeout: bool = Field(default=True)
    retry_on_worker_lost: bool = Field(default=False)