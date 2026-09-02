from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.api.deps import get_db_session
from app.core.password import hash_password
from app.models.user import User, UserRole
from app.repositories.user_repo import get_user_by_id, get_user_by_username, list_users
from app.schemas.user import UserCreate
from app.services.auth_service import register_user
from app.ui.deps import get_web_admin

router = APIRouter(tags=["UI-Administration"])

templates = Jinja2Templates(directory="app/templates")


def render_users_panel(
    request: Request,
    session: Session,
    current_user: User,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="components/users_panel.html",
        context={
            "current_user": current_user,
            "users": list_users(session),
            "user_roles": list(UserRole),
            "message": message,
            "error": error,
        },
    )


@router.get("/administration", name="administration")
def administration_page(
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    return templates.TemplateResponse(
        request=request,
        name="pages/administration.html",
        context={
            "page_title": "Administration",
            "page_name": "administration",
            "active_page": "administration",
            "current_user": current_user,
            "users": list_users(session),
            "user_roles": list(UserRole),
        },
    )


@router.post("/administration/users/create", response_class=HTMLResponse)
def create_user_from_administration(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(default=""),
    full_name: str = Form(default=""),
    role: UserRole = Form(default=UserRole.VIEWER),
    is_active: bool = Form(default=False),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    username = username.strip()
    email = email.strip()
    full_name = full_name.strip()

    if len(username) < 3:
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error="Username must be at least 3 characters.",
        )

    if len(password) < 8:
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error="Password must be at least 8 characters.",
        )

    if get_user_by_username(session, username) is not None:
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error="Username already exists.",
        )

    try:
        user_in = UserCreate(
            username=username,
            email=email or None,
            full_name=full_name or None,
            password=password,
            role=role,
            is_active=is_active,
            is_superuser=False,
        )
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {}
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error=str(first_error.get("msg", "Invalid user data.")),
        )

    register_user(session, user_in)

    return render_users_panel(
        request=request,
        session=session,
        current_user=current_user,
        message=f"User '{username}' created.",
    )


@router.post("/administration/users/{user_id}/update", response_class=HTMLResponse)
def update_user_from_administration(
    user_id: int,
    request: Request,
    role: UserRole = Form(...),
    is_active: bool = Form(default=False),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    user = get_user_by_id(session, user_id)
    if user is None:
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error="User not found.",
        )

    if user.id == current_user.id:
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error="You cannot change your own role or active status here.",
        )

    user.role = role
    user.is_active = is_active
    user.updated_at = datetime.utcnow()
    session.add(user)
    session.commit()

    return render_users_panel(
        request=request,
        session=session,
        current_user=current_user,
        message=f"User '{user.username}' updated.",
    )


@router.post("/administration/users/{user_id}/reset-password", response_class=HTMLResponse)
def reset_user_password_from_administration(
    user_id: int,
    request: Request,
    password: str = Form(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    user = get_user_by_id(session, user_id)
    if user is None:
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error="User not found.",
        )

    if user.id == current_user.id:
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error="Use Change Password to update your own password.",
        )

    if len(password) < 8:
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error="Password must be at least 8 characters.",
        )

    user.hashed_password = hash_password(password)
    user.updated_at = datetime.utcnow()
    session.add(user)
    session.commit()

    return render_users_panel(
        request=request,
        session=session,
        current_user=current_user,
        message=f"Password reset for '{user.username}'.",
    )


@router.post("/administration/users/{user_id}/delete", response_class=HTMLResponse)
def delete_user_from_administration(
    user_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    user = get_user_by_id(session, user_id)
    if user is None:
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error="User not found.",
        )

    if user.id == current_user.id:
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error="You cannot delete your own account.",
        )

    username = user.username

    try:
        session.delete(user)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        return render_users_panel(
            request=request,
            session=session,
            current_user=current_user,
            error=(
                f"User '{username}' cannot be deleted because related records "
                "still reference this account. Disable the user instead."
            ),
        )

    return render_users_panel(
        request=request,
        session=session,
        current_user=current_user,
        message=f"User '{username}' deleted.",
    )
