from datetime import datetime, timedelta

from sqlmodel import Session

from app.config import get_settings
from app.core.password import hash_password, verify_password
from app.core.tokens import create_access_token
from app.models.user import User, UserRole
from app.repositories.user_repo import create_user, get_user_by_username
from app.schemas.auth import TokenResponse
from app.schemas.user import UserCreate

settings = get_settings()


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(session, username)

    if user is None:
        return None

    if not user.is_active:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


def login_user(session: Session, username: str, password: str) -> TokenResponse | None:
    user = authenticate_user(session, username, password)

    if user is None:
        return None

    access_token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(access_token=access_token)


def register_user(session: Session, user_in: UserCreate) -> User:
    user = User(
        username=user_in.username,
        email=str(user_in.email) if user_in.email else None,
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
        role=user_in.role,
        is_active=user_in.is_active,
        is_superuser=user_in.is_superuser,
    )

    return create_user(session, user)


def change_user_password(
    session: Session,
    user: User,
    current_password: str,
    new_password: str,
) -> bool:
    if not verify_password(current_password, user.hashed_password):
        return False

    user.hashed_password = hash_password(new_password)
    user.updated_at = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)

    return True


def create_initial_admin(
    session: Session,
    username: str,
    password: str,
    email: str | None = None,
    full_name: str | None = None,
) -> User:
    existing_user = get_user_by_username(session, username)

    if existing_user is not None:
        return existing_user

    user = User(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=UserRole.ADMIN,
        is_active=True,
        is_superuser=True,
    )

    return create_user(session, user)
