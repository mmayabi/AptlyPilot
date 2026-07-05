from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.api.deps import get_db_session
from app.models.user import User
from app.services.aptly_dashboard_service import (
    get_dashboard_compliance,
    get_dashboard_provider_release_detail,
    get_dashboard_provider_releases,
    get_dashboard_providers,
    get_dashboard_repositories,
    get_dashboard_repository_by_id,
    get_dashboard_repository_by_name,
    get_dashboard_summary,
)
from app.ui.deps import get_web_viewer

router = APIRouter(tags=["UI-dashboard"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/", name="dashboard")
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

#@router.get("/", response_class=HTMLResponse)
#def ui_home(request: Request):
#    return templates.TemplateResponse(
#        request=request,
#        name="pages/dashboard.html",
#        context={
#            "page_title": "Dashboard",
#        },
#    )


