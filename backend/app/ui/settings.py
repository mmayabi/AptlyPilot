from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.api.deps import get_db_session
from app.clients.aptly_client import AptlyClient
from app.config import get_settings
from app.models.user import User
from app.schemas.repo import ConfigValidationResponse
from app.services.app_setting_service import (
    get_aptly_connection_values,
    get_app_setting_value,
    save_aptly_connection_settings,
    save_config_source_settings,
)
from app.services.config_loader_service import (
    get_repos_config_path,
    get_repos_config_location,
    get_repos_config_source,
    is_local_repos_config_source,
    load_repos_config_text,
    save_repos_config_text,
    validate_repos_config_text,
)
from app.services.repo_service import sync_repos_from_config, validate_config_file
from app.ui.deps import get_web_admin

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
    current_user: User = Depends(get_web_admin),
):
    settings = get_settings()
    config_path = get_repos_config_path()
    config_source = get_repos_config_source()
    config_is_local = is_local_repos_config_source()
    validation = validate_config_file()
    config_content = ""
    config_read_error = None

    try:
        config_content = load_repos_config_text()
    except Exception as exc:
        config_read_error = str(exc)

    aptly_connection = get_aptly_connection_values()

    return templates.TemplateResponse(
        request=request,
        name="pages/settings.html",
        context={
            "page_title": "Settings",
            "page_name": "settings",
            "active_page": "settings",
            "current_user": current_user,
            "runtime_settings": get_runtime_settings(),
            "aptly_connection": {
                **aptly_connection,
                "has_password": bool(aptly_connection["password"]),
                "has_token": bool(aptly_connection["token"]),
            },
            "config_source": config_source,
            "config_location": get_repos_config_location(),
            "config_is_local": config_is_local,
            "config_source_values": {
                "source": get_app_setting_value("REPOS_CONFIG_SOURCE", settings.REPOS_CONFIG_SOURCE)
                or "local",
                "local_path": get_app_setting_value("REPOS_CONFIG_PATH", settings.REPOS_CONFIG_PATH)
                or "",
                "gitlab_base_url": get_app_setting_value(
                    "GITLAB_CONFIG_BASE_URL",
                    settings.GITLAB_CONFIG_BASE_URL,
                )
                or "",
                "gitlab_project_id": get_app_setting_value(
                    "GITLAB_CONFIG_PROJECT_ID",
                    settings.GITLAB_CONFIG_PROJECT_ID or "",
                )
                or "",
                "gitlab_ref": get_app_setting_value("GITLAB_CONFIG_REF", settings.GITLAB_CONFIG_REF)
                or "main",
                "gitlab_file_path": get_app_setting_value(
                    "GITLAB_CONFIG_FILE_PATH",
                    settings.GITLAB_CONFIG_FILE_PATH or "",
                )
                or "",
                "gitlab_timeout_seconds": get_app_setting_value(
                    "GITLAB_CONFIG_TIMEOUT_SECONDS",
                    str(settings.GITLAB_CONFIG_TIMEOUT_SECONDS),
                )
                or "20",
                "has_gitlab_token": bool(
                    get_app_setting_value(
                        "GITLAB_CONFIG_TOKEN",
                        settings.GITLAB_CONFIG_TOKEN or "",
                    )
                ),
            },
            "config_path": str(config_path),
            "config_path_exists": Path(config_path).exists() if config_is_local else None,
            "config_validation": validation,
            "config_content": config_content,
            "config_read_error": config_read_error,
        },
    )


@router.post("/settings/aptly-connection/save", response_class=HTMLResponse)
def save_aptly_connection(
    request: Request,
    aptly_api_url: str = Form(...),
    aptly_api_username: str = Form(default=""),
    aptly_api_password: str = Form(default=""),
    aptly_api_token: str = Form(default=""),
    clear_aptly_password: bool = Form(default=False),
    clear_aptly_token: bool = Form(default=False),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    save_aptly_connection_settings(
        api_url=aptly_api_url,
        username=aptly_api_username,
        password=aptly_api_password,
        token=aptly_api_token,
        clear_password=clear_aptly_password,
        clear_token=clear_aptly_token,
        session=session,
    )

    return templates.TemplateResponse(
        request=request,
        name="components/settings_save_result.html",
        context={
            "current_user": current_user,
            "message": "Aptly connection settings saved.",
        },
    )


@router.post("/settings/aptly-connection/test", response_class=HTMLResponse)
def test_aptly_connection(
    request: Request,
    aptly_api_url: str | None = Form(default=None),
    aptly_api_username: str = Form(default=""),
    aptly_api_password: str = Form(default=""),
    aptly_api_token: str = Form(default=""),
    current_user: User = Depends(get_web_admin),
):
    try:
        saved_values = get_aptly_connection_values()
        client = AptlyClient(
            base_url=aptly_api_url or saved_values["url"],
            username=aptly_api_username or saved_values["username"] or None,
            password=aptly_api_password or saved_values["password"] or None,
            token=aptly_api_token or saved_values["token"] or None,
        )
        mirrors = client.list_mirrors()
        return templates.TemplateResponse(
            request=request,
            name="components/settings_save_result.html",
            context={
                "current_user": current_user,
                "message": f"Connected to Aptly successfully. Mirrors found: {len(mirrors)}.",
            },
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request=request,
            name="components/settings_error_result.html",
            context={
                "current_user": current_user,
                "message": str(exc),
            },
        )


@router.post("/settings/config-source/save", response_class=HTMLResponse)
def save_config_source(
    request: Request,
    source: str = Form(...),
    gitlab_base_url: str = Form(...),
    gitlab_project_id: str = Form(default=""),
    gitlab_ref: str = Form(default="main"),
    gitlab_file_path: str = Form(default=""),
    gitlab_token: str = Form(default=""),
    clear_gitlab_token: bool = Form(default=False),
    gitlab_timeout_seconds: int = Form(default=20),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    save_config_source_settings(
        source=source,
        gitlab_base_url=gitlab_base_url,
        gitlab_project_id=gitlab_project_id,
        gitlab_ref=gitlab_ref,
        gitlab_file_path=gitlab_file_path,
        gitlab_token=gitlab_token,
        clear_gitlab_token=clear_gitlab_token,
        gitlab_timeout_seconds=gitlab_timeout_seconds,
        session=session,
    )

    return templates.TemplateResponse(
        request=request,
        name="components/settings_save_result.html",
        context={
            "current_user": current_user,
            "message": "Config source settings saved. Reload the page to fetch the selected source.",
        },
        headers={"HX-Refresh": "true"},
    )


@router.post("/settings/config/validate", response_class=HTMLResponse)
def validate_current_config_text(
    request: Request,
    config_content: str = Form(...),
    current_user: User = Depends(get_web_admin),
):
    validation = validate_repos_config_text(config_content)

    return templates.TemplateResponse(
        request=request,
        name="components/config_validation_result.html",
        context={
            "current_user": current_user,
            "title": "Editor Validation",
            "validation": validation,
            "saved": False,
        },
    )


@router.post("/settings/config/save", response_class=HTMLResponse)
def save_current_config_text(
    request: Request,
    config_content: str = Form(...),
    current_user: User = Depends(get_web_admin),
):
    validation = save_repos_config_text(config_content)

    return templates.TemplateResponse(
        request=request,
        name="components/config_validation_result.html",
        context={
            "current_user": current_user,
            "title": "Save Config",
            "validation": validation,
            "saved": validation.valid,
        },
    )


@router.post("/settings/config/save-and-sync", response_class=HTMLResponse)
def save_and_sync_current_config_text(
    request: Request,
    config_content: str = Form(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    validation = save_repos_config_text(config_content)
    sync_result = None

    if validation.valid:
        sync_result = sync_repos_from_config(session)

    return templates.TemplateResponse(
        request=request,
        name="components/config_validation_result.html",
        context={
            "current_user": current_user,
            "title": "Save & Sync Config",
            "validation": validation,
            "saved": validation.valid,
            "sync_result": sync_result,
        },
    )


@router.post("/settings/config/sync-current", response_class=HTMLResponse)
def sync_current_config_source(
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    validation = validate_config_file()
    sync_result = None

    if validation.valid:
        sync_result = sync_repos_from_config(session)

    return templates.TemplateResponse(
        request=request,
        name="components/config_validation_result.html",
        context={
            "current_user": current_user,
            "title": "Sync Current Source",
            "validation": validation,
            "saved": False,
            "sync_result": sync_result,
        },
    )


@router.post("/settings/config/upload-test", response_class=HTMLResponse)
async def validate_uploaded_config_file(
    request: Request,
    config_file: UploadFile = File(...),
    current_user: User = Depends(get_web_admin),
):
    raw_content = await config_file.read()

    try:
        config_content = raw_content.decode("utf-8")
        validation = validate_repos_config_text(config_content)
    except UnicodeDecodeError as exc:
        validation = ConfigValidationResponse(
            valid=False,
            repo_count=0,
            repos=[],
            errors=[f"Uploaded file is not valid UTF-8: {exc}"],
        )

    return templates.TemplateResponse(
        request=request,
        name="components/config_validation_result.html",
        context={
            "current_user": current_user,
            "title": f"Upload Validation: {config_file.filename}",
            "validation": validation,
            "saved": False,
        },
    )
