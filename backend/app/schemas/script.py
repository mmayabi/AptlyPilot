from typing import Any
from pydantic import BaseModel, Field


class ScriptRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)