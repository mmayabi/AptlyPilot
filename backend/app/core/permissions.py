from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_active_user
from app.models.user import User, UserRole


def require_roles(*allowed_roles: UserRole) -> Callable:
    def dependency(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.is_superuser:
            return current_user

        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        return current_user

    return dependency


require_admin = require_roles(UserRole.ADMIN)
require_operator = require_roles(UserRole.ADMIN, UserRole.OPERATOR)
require_viewer = require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER)