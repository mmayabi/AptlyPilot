from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.api.deps import get_db_session
from app.models.user import User
from app.services.aptly_dashboard_service import get_dashboard_summary
from app.services.aptly_inventory_service import sync_aptly_inventory
from app.services.repo_service import sync_repos_from_config, validate_config_file
from app.ui.deps import get_ui_aptly_client, get_web_admin, get_web_operator, get_web_viewer

router = APIRouter(tags=["UI-dashboard"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/", name="dashboard")
@router.get("/dashboard", name="dashboard_alias")
def dashboard(
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    overview = get_dashboard_summary(session)

    return templates.TemplateResponse(
        request=request,
        name="pages/dashboard.html",
        context={
            "page_title": "Dashboard",
            "page_name": "dashboard",
            "active_page": "dashboard",
            "current_user": current_user,
            "overview": overview,
        },
    )


@router.post("/dashboard/sync-aptly", response_class=HTMLResponse)
def dashboard_sync_aptly(
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_operator),
    aptly_client = Depends(get_ui_aptly_client),
):
    sync_result = sync_aptly_inventory(
        session=session,
        aptly_client=aptly_client,
    )
    overview = get_dashboard_summary(session)

    return templates.TemplateResponse(
        request=request,
        name="components/dashboard_sync_panels.html",
        context={
            "current_user": current_user,
            "overview": overview,
            "sync_result": sync_result,
            "sync_result_title": "Refresh Actual State",
        },
    )


@router.post("/dashboard/sync-from-config", response_class=HTMLResponse)
def dashboard_sync_from_config(
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    validation = validate_config_file()
    if not validation.valid:
        return templates.TemplateResponse(
            request=request,
            name="components/sync_actions_card.html",
            context={
                "current_user": current_user,
                "overview": get_dashboard_summary(session),
                "sync_result": {
                    "status": "failed",
                    "errors": validation.errors,
                },
                "sync_result_title": "Sync Expected Config",
            },
            status_code=400,
        )

    result = sync_repos_from_config(session)
    overview = get_dashboard_summary(session)

    return templates.TemplateResponse(
        request=request,
        name="components/sync_actions_card.html",
        context={
            "current_user": current_user,
            "overview": overview,
            "sync_result": {
                "status": "success",
                "created": result.created,
                "updated": result.updated,
                "disabled": result.disabled,
                "total": result.total,
            },
            "sync_result_title": "Sync Expected Config",
        },
    )
