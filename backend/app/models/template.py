# file: app/models/template.py

from datetime import datetime
from sqlmodel import SQLModel, Field
from app.models.script import Script

# ------------------------------
# JobTemplate Table
# ------------------------------
class JobTemplate(SQLModel, table=True):
    """
    جدول JobTemplate: تعریف blueprint کلی job.
    شامل نام، توضیح و کاربر سازنده template.
    """
    __tablename__ = "job_templates"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, unique=True)
    description: str | None = None
    created_by: int | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ------------------------------
# JobStepTemplate Table
# ------------------------------
class JobStepTemplate(SQLModel, table=True):
    """
    جدول JobStepTemplate: تعریف blueprint هر step در یک JobTemplate.
    نگهداری ارتباط با Script، ترتیب اجرا و توضیحات کوتاه.
    """
    __tablename__ = "job_step_templates"

    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="job_templates.id", index=True)
    script_id: int = Field(foreign_key="scripts.id")  # لینک به جدول Script
    order: int = Field(default=0)  # ترتیب اجرای step
    description: str | None = None