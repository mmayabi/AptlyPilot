from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.api.deps import get_db_session
from app.services.auth_service import login_user

router = APIRouter(tags=["Authentication"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/login", name="login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="pages/login.html",
        context={
            "page_title": "Sign In",
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
