from sqlmodel import Session, select

from app.models.user import User


def count_users(session: Session) -> int:
    return len(list_users(session))


def list_users(session: Session) -> list[User]:
    statement = select(User).order_by(User.username)
    return list(session.exec(statement).all())


def get_user_by_username(session: Session, username: str) -> User | None:
    statement = select(User).where(User.username == username)
    return session.exec(statement).first()


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def create_user(session: Session, user: User) -> User:
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
