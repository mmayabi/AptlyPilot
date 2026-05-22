# file: app/models/script.py

from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB

class Script(SQLModel, table=True):
    """
    جدول Script: تعریف scriptهای قابل اجرا توسط Worker.
    نگهداری نام script، توضیحات و پارامترهای ورودی مورد نیاز (required/optional).
    """
    __tablename__ = "scripts"

    id: int | None = Field(default=None, primary_key=True)
    name: str  # نام script، مثال: mirror_update.py
    description: str | None = None
    params: dict | None = Field(default_factory=dict, sa_column=Column(JSONB))
    # params = {"mirror": {"required": True}, "url": {"required": True}}