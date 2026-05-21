from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr | None = None
    full_name: str | None = None
    role: UserRole
    is_active: bool
    is_superuser: bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str
    email: EmailStr | None = None
    full_name: str | None = None
    password: str
    role: UserRole = UserRole.VIEWER
    is_active: bool = True
    is_superuser: bool = False