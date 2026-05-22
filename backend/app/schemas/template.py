from pydantic import BaseModel, Field


class JobStepTemplateCreate(BaseModel):
    script_id: int
    order: int = 0
    description: str | None = None


class JobTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    steps: list[JobStepTemplateCreate] = Field(default_factory=list)


class JobStepTemplateUpdate(BaseModel):
    # اگر id نداشته باشد، یعنی step جدید باید ساخته شود
    id: int | None = None
    script_id: int
    order: int = 0
    description: str | None = None


class JobTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None

    # اگر None باشد یعنی steps تغییر نکند
    # اگر [] باشد یعنی همه steps حذف شوند
    steps: list[JobStepTemplateUpdate] | None = None


class JobStepTemplateRead(BaseModel):
    id: int
    script_id: int
    order: int
    description: str | None = None


class JobTemplateRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    steps: list[JobStepTemplateRead] = Field(default_factory=list)