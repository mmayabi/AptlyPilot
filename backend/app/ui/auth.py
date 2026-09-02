from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.api.deps import get_db_session
from app.models.user import User
from app.repositories.user_repo import count_users
from app.services.auth_service import change_user_password, create_initial_admin, login_user
from app.ui.deps import get_web_viewer

router = APIRouter(tags=["Authentication"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/login", name="login")
def login_page(
    request: Request,
    session: Session = Depends(get_db_session),
):
    if count_users(session) == 0:
        return templates.TemplateResponse(
            request=request,
            name="pages/setup.html",
            context={
                "page_title": "Initial Setup",
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="pages/login.html",
        context={
            "page_title": "Sign In",
        },
    )


@router.post("/setup", name="setup")
def setup_initial_admin(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    email: str = Form(default=""),
    full_name: str = Form(default=""),
    session: Session = Depends(get_db_session),
):
    if count_users(session) > 0:
        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    username = username.strip()
    email = email.strip()
    full_name = full_name.strip()

    if len(username) < 3:
        return templates.TemplateResponse(
            request=request,
            name="pages/setup.html",
            context={
                "page_title": "Initial Setup",
                "error": "Username must be at least 3 characters.",
                "username": username,
                "email": email,
                "full_name": full_name,
            },
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="pages/setup.html",
            context={
                "page_title": "Initial Setup",
                "error": "Password must be at least 8 characters.",
                "username": username,
                "email": email,
                "full_name": full_name,
            },
        )

    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="pages/setup.html",
            context={
                "page_title": "Initial Setup",
                "error": "Password and confirmation do not match.",
                "username": username,
                "email": email,
                "full_name": full_name,
            },
        )

    admin = create_initial_admin(
        session=session,
        username=username,
        password=password,
        email=email or None,
        full_name=full_name or None,
    )

    token = login_user(
        session=session,
        username=admin.username,
        password=password,
    )

    response = RedirectResponse(
        url="/",
        status_code=303,
    )

    if token is not None:
        response.set_cookie(
            key="access_token",
            value=token.access_token,
            httponly=True,
            secure=False,          # True in production
            samesite="lax",
            path="/",
            max_age=3600,
        )

    return response


@router.get("/account", name="account")
def account_page(
    request: Request,
    current_user: User = Depends(get_web_viewer),
):
    return templates.TemplateResponse(
        request=request,
        name="pages/account.html",
        context={
            "page_title": "Account",
            "page_name": "account",
            "active_page": "account",
            "current_user": current_user,
        },
    )


@router.post("/login", name="login_post")
def login(
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_db_session),
):

    token = login_user(
        session=session,
        username=username,
        password=password,
    )

    if token is None:
        return RedirectResponse(
            url="/login?error=1",
            status_code=303,
        )

    response = RedirectResponse(
        url="/",
        status_code=303,
    )

    response.set_cookie(
        key="access_token",
        value=token.access_token,
        httponly=True,
        secure=False,          # True in production
        samesite="lax",
        path="/",
        max_age=3600,
    )

    return response


@router.post("/logout", name="logout")
def logout():

    response = RedirectResponse(
        url="/login",
        status_code=303,
    )

    response.delete_cookie(
        key="access_token",
        path="/",
    )

    return response


@router.post("/account/password", name="change_password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    if len(new_password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="components/settings_error_result.html",
            context={
                "current_user": current_user,
                "message": "New password must be at least 8 characters.",
            },
        )

    if new_password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="components/settings_error_result.html",
            context={
                "current_user": current_user,
                "message": "New password and confirmation do not match.",
            },
        )

    changed = change_user_password(
        session=session,
        user=current_user,
        current_password=current_password,
        new_password=new_password,
    )

    if not changed:
        return templates.TemplateResponse(
            request=request,
            name="components/settings_error_result.html",
            context={
                "current_user": current_user,
                "message": "Current password is incorrect.",
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="components/settings_save_result.html",
        context={
            "current_user": current_user,
            "message": "Password changed successfully.",
        },
    )
