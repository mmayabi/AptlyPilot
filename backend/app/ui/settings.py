from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.models.user import User
from app.services.config_loader_service import (
    get_repos_config_path,
    load_repos_config_text,
)
from app.services.repo_service import validate_config_file
from app.ui.deps import get_web_viewer

router = APIRouter(tags=["UI-Settings"])

templates = Jinja2Templates(directory="app/templates")


def mask_secret(value: str | None) -> str:
    if not value:
        return "-"
    return "********"


def get_runtime_settings() -> list[dict[str, str]]:
    settings = get_settings()

    return [
        {"key": "ENVIRONMENT", "value": settings.ENVIRONMENT},
        {"key": "DEBUG", "value": str(settings.DEBUG)},
        {"key": "LOG_LEVEL", "value": settings.LOG_LEVEL},
        {"key": "API_V1_PREFIX", "value": settings.API_V1_PREFIX},
        {"key": "REPOS_CONFIG_PATH", "value": settings.REPOS_CONFIG_PATH},
        {"key": "APTLY_API_URL", "value": settings.APTLY_API_URL},
        {"key": "APTLY_API_USERNAME", "value": settings.APTLY_API_USERNAME or "-"},
        {"key": "APTLY_API_PASSWORD", "value": mask_secret(settings.APTLY_API_PASSWORD)},
        {"key": "APTLY_API_TOKEN", "value": mask_secret(settings.APTLY_API_TOKEN)},
        {"key": "ENABLE_IN_APP_WORKER", "value": str(settings.ENABLE_IN_APP_WORKER)},
        {"key": "ENABLE_IN_APP_SCHEDULER", "value": str(settings.ENABLE_IN_APP_SCHEDULER)},
        {
            "key": "WORKER_POLL_INTERVAL_SECONDS",
            "value": str(settings.WORKER_POLL_INTERVAL_SECONDS),
        },
        {
            "key": "SCHEDULER_POLL_INTERVAL_SECONDS",
            "value": str(settings.SCHEDULER_POLL_INTERVAL_SECONDS),
        },
    ]


@router.get("/settings", name="settings")
def settings_page(
    request: Request,
    current_user: User = Depends(get_web_viewer),
):
    config_path = get_repos_config_path()
    validation = validate_config_file()
    config_content = ""
    config_read_error = None

    try:
        config_content = load_repos_config_text()
    except Exception as exc:
        config_read_error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="pages/settings.html",
        context={
            "page_title": "Settings",
            "page_name": "settings",
            "active_page": "settings",
            "current_user": current_user,
            "runtime_settings": get_runtime_settings(),
            "config_path": str(config_path),
            "config_path_exists": Path(config_path).exists(),
            "config_validation": validation,
            "config_content": config_content,
            "config_read_error": config_read_error,
        },
    )
