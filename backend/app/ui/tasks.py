from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.api.deps import get_db_session
from app.models.user import User
from app.models.worker_queue import WorkerQueueRequestedBy, WorkerQueueStatus
from app.services.repo_service import get_all_repos
from app.services.worker_queue_service import (
    cancel_pipeline_execution,
    list_worker_pipeline_run_details,
)
from app.ui.deps import get_web_operator, get_web_viewer

router = APIRouter(tags=["UI-Tasks"])

templates = Jinja2Templates(directory="app/templates")


def _parse_repo_id(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


def _parse_status_filter(value: str | None) -> WorkerQueueStatus | None:
    if not value:
        return None
    return WorkerQueueStatus(value)


def _parse_requested_by(value: str | None) -> WorkerQueueRequestedBy | None:
    if not value:
        return None
    return WorkerQueueRequestedBy(value)


def _load_pipeline_runs(
    session: Session,
    status_filter: WorkerQueueStatus | None,
    repo_id: int | None,
    requested_by: WorkerQueueRequestedBy | None,
) -> list[dict]:
    return list_worker_pipeline_run_details(
        session=session,
        status_filter=status_filter,
        repo_id=repo_id,
        requested_by=requested_by,
        limit=100,
    )


@router.get("/tasks", name="tasks")
def tasks(
    request: Request,
    status_filter: str | None = Query(default=None),
    repo_id: str | None = Query(default=None),
    requested_by: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    parsed_status_filter = _parse_status_filter(status_filter)
    parsed_repo_id = _parse_repo_id(repo_id)
    parsed_requested_by = _parse_requested_by(requested_by)
    repos = get_all_repos(session)
    pipeline_runs = _load_pipeline_runs(
        session=session,
        status_filter=parsed_status_filter,
        repo_id=parsed_repo_id,
        requested_by=parsed_requested_by,
    )

    return templates.TemplateResponse(
        request=request,
        name="pages/tasks.html",
        context={
            "page_title": "Tasks",
            "page_name": "tasks",
            "active_page": "tasks",
            "current_user": current_user,
            "repos": repos,
            "pipeline_runs": pipeline_runs,
            "status_filter": parsed_status_filter,
            "repo_id": parsed_repo_id,
            "requested_by": parsed_requested_by,
        },
    )


@router.get("/tasks/runs", response_class=HTMLResponse)
def task_runs(
    request: Request,
    status_filter: str | None = Query(default=None),
    repo_id: str | None = Query(default=None),
    requested_by: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    pipeline_runs = _load_pipeline_runs(
        session=session,
        status_filter=_parse_status_filter(status_filter),
        repo_id=_parse_repo_id(repo_id),
        requested_by=_parse_requested_by(requested_by),
    )

    return templates.TemplateResponse(
        request=request,
        name="components/task_runs_table.html",
        context={
            "current_user": current_user,
            "pipeline_runs": pipeline_runs,
        },
    )


@router.post("/tasks/executions/{execution_id}/cancel", response_class=HTMLResponse)
def cancel_task_execution(
    request: Request,
    execution_id: str,
    status_filter: str | None = Query(default=None),
    repo_id: str | None = Query(default=None),
    requested_by: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_operator),
):
    cancel_pipeline_execution(
        execution_id=execution_id,
        session=session,
    )

    pipeline_runs = _load_pipeline_runs(
        session=session,
        status_filter=_parse_status_filter(status_filter),
        repo_id=_parse_repo_id(repo_id),
        requested_by=_parse_requested_by(requested_by),
    )

    return templates.TemplateResponse(
        request=request,
        name="components/task_runs_table.html",
        context={
            "current_user": current_user,
            "pipeline_runs": pipeline_runs,
        },
    )
