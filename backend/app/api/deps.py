from collections.abc import Generator

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.config import get_settings
from app.core.tokens import decode_access_token
from app.db.session import get_session
from app.models.user import User
from app.repositories.user_repo import get_user_by_id

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=False,
)


def get_db_session() -> Generator[Session, None, None]:
    yield from get_session()


def get_access_token(
    request: Request,
    bearer_token: str | None = Depends(oauth2_scheme),
) -> str:
    if bearer_token:
        return bearer_token

    cookie_token = request.cookies.get("access_token")

    if cookie_token:
        return cookie_token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

def get_current_user(
    token: str = Depends(get_access_token),
    session: Session = Depends(get_db_session),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception

        user_id = int(subject)
    except Exception as exc:
        raise credentials_exception from exc

    user = get_user_by_id(session, user_id)

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return current_user
