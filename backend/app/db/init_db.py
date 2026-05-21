from sqlmodel import SQLModel

from app.db import base  # noqa: F401
from app.db.session import engine


def init_db() -> None:
    SQLModel.metadata.create_all(engine)