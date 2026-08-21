from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.api.deps import get_db_session
from app.clients.aptly_client import AptlyClient
from app.core.tokens import decode_access_token
from app.models.user import User
from app.models.user import UserRole
from app.repositories.user_repo import get_user_by_id
from app.services.app_setting_service import make_aptly_client_from_settings


def _get_web_user_with_roles(
    allowed_roles: set[UserRole],
    request: Request,
    session: Session,
) -> User:
    redirect_to_login = HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        detail="Not authenticated",
        headers={
            "Location": "/login",
            "HX-Redirect": "/login",
        },
    )

    token = request.cookies.get("access_token")
    if not token:
        raise redirect_to_login

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if subject is None:
            raise ValueError("Missing token subject")

        user_id = int(subject)
    except Exception as exc:
        raise redirect_to_login from exc

    user = get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise redirect_to_login

    if user.is_superuser or user.role in allowed_roles:
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
    )


def get_web_viewer(
    request: Request,
    session: Session = Depends(get_db_session),
) -> User:
    """
    Authentication dependency for HTML UI pages.

    API dependencies should keep returning 401/403 JSON responses, but browser
    pages should send unauthenticated users back to the sign-in screen.
    """

    return _get_web_user_with_roles(
        allowed_roles={UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER},
        request=request,
        session=session,
    )


def get_web_operator(
    request: Request,
    session: Session = Depends(get_db_session),
) -> User:
    return _get_web_user_with_roles(
        allowed_roles={UserRole.ADMIN, UserRole.OPERATOR},
        request=request,
        session=session,
    )


def get_web_admin(
    request: Request,
    session: Session = Depends(get_db_session),
) -> User:
    return _get_web_user_with_roles(
        allowed_roles={UserRole.ADMIN},
        request=request,
        session=session,
    )


def get_ui_aptly_client() -> AptlyClient:
    return make_aptly_client_from_settings()
