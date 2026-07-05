from fastapi import Depends

from app.core.permissions import require_viewer
from app.models.user import User


def get_web_viewer(
    current_user: User = Depends(require_viewer),
) -> User:
    """
    Authentication dependency for UI pages.
    """

    return current_user