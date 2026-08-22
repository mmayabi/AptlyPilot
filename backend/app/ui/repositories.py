from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.api.deps import get_db_session
from app.models.repo import Repo
from app.models.user import User
from app.services.aptly_dashboard_service import (
    get_dashboard_providers,
    get_dashboard_provider_releases,
    get_dashboard_provider_release_detail,
    get_dashboard_repository_by_id,
)
from app.services.aptly_inventory_service import sync_aptly_inventory
from app.services.repo_service import (
    sync_repos_from_config,
    validate_config_file,
)
from app.services.worker_queue_service import (
    enqueue_repository_pipeline,
    list_worker_queue_run_details_for_repo,
    worker_queue_to_read,
)
from app.ui.deps import get_ui_aptly_client, get_web_admin, get_web_operator, get_web_viewer

router = APIRouter(tags=["UI-Repositories"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/repositories", name="repositories")
def repositories(
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    providers = get_dashboard_providers(session)

    return templates.TemplateResponse(
        request=request,
        name="pages/repositories.html",
        context={
            "page_title": "Repositories",
            "page_name": "repositories",
            "active_page": "repositories",
            "current_user": current_user,
            "providers": providers,
        },
    )


@router.post(
    "/repositories/sync-aptly",
    response_class=HTMLResponse,
)
def repositories_sync_aptly(
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_operator),
    aptly_client = Depends(get_ui_aptly_client),
):
    result = sync_aptly_inventory(
        session=session,
        aptly_client=aptly_client,
    )

    return templates.TemplateResponse(
        request=request,
        name="components/sync_result.html",
        context={
            "current_user": current_user,
            "title": "Refresh Actual State",
            "description": "Read the current mirror, snapshot, and publish state from Aptly.",
            "result": result,
        },
    )


@router.post(
    "/repositories/sync-from-config",
    response_class=HTMLResponse,
)
def repositories_sync_from_config(
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    validation = validate_config_file()
    if not validation.valid:
        return templates.TemplateResponse(
            request=request,
            name="components/sync_result.html",
            context={
                "current_user": current_user,
                "title": "Sync Expected Config",
                "description": "The expected repository config could not be loaded.",
                "result": {
                    "status": "failed",
                    "errors": validation.errors,
                },
            },
            status_code=400,
        )

    result = sync_repos_from_config(session)

    return templates.TemplateResponse(
        request=request,
        name="components/sync_result.html",
        context={
            "current_user": current_user,
            "title": "Sync Expected Config",
            "description": "Sync the expected repository config into the database.",
            "result": {
                "status": "success",
                "created": result.created,
                "updated": result.updated,
                "disabled": result.disabled,
                "total": result.total,
            },
        },
    )


@router.get(
    "/repositories/providers/{provider}/releases",
    response_class=HTMLResponse,
)
def provider_releases(
    request: Request,
    provider: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    releases = get_dashboard_provider_releases(
        session=session,
        provider=provider,
    )

    return templates.TemplateResponse(
        request=request,
        name="components/rows_release.html",
        context={
            "releases": releases,
            "current_user": current_user,
        },
    )


@router.get(
    "/repositories/providers/{provider}/releases/{release}",
    response_class=HTMLResponse,
)
def release_repositories(
    request: Request,
    provider: str,
    release: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    detail = get_dashboard_provider_release_detail(
        session=session,
        provider=provider,
        release=release,
    )

    return templates.TemplateResponse(
        request=request,
        name="components/rows_repository.html",
        context={
            "repositories": detail["repositories"],
            "provider": provider,
            "release": release,
            "current_user": current_user,
        },
    )


@router.post(
    "/repositories/{repo_id}/run-pipeline",
    response_class=HTMLResponse,
)
def run_repository_pipeline_from_ui(
    request: Request,
    repo_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_operator),
):
    try:
        queue_item = enqueue_repository_pipeline(
            repo_id=repo_id,
            session=session,
            requested_by_user_id=current_user.id,
        )
    except HTTPException as exc:
        return templates.TemplateResponse(
            request=request,
            name="components/operation_run_result.html",
            context={
                "current_user": current_user,
                "queue_item": None,
                "error": exc.detail,
            },
            status_code=exc.status_code,
        )

    return templates.TemplateResponse(
        request=request,
        name="components/operation_run_result.html",
        context={
            "current_user": current_user,
            "queue_item": worker_queue_to_read(queue_item),
            "error": None,
        },
    )


@router.get(
    "/repositories/{repo_id}/runs",
    response_class=HTMLResponse,
)
def repository_operation_runs(
    request: Request,
    repo_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")

    run_details = list_worker_queue_run_details_for_repo(
        repo_id=repo.id,
        session=session,
        limit=20,
    )

    return templates.TemplateResponse(
        request=request,
        name="components/operation_runs.html",
        context={
            "current_user": current_user,
            "run_details": run_details,
        },
    )


@router.get(
    "/repositories/{repo_id}",
    response_class=HTMLResponse,
)
def repository_details(
    request: Request,
    repo_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    repository = get_dashboard_repository_by_id(
        session=session,
        repo_id=repo_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="components/repository_drawer.html",
        context={
            "repository": repository,
            "current_user": current_user,
        },
    )
