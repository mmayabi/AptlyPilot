from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.api.deps import get_db_session
from app.models.job import Job
from app.models.job_schedule import JobScheduleStatus
from app.models.user import User
from app.services.job_schedule_service import get_schedule, list_schedule_details
from app.services.repo_service import get_all_repos
from app.services.worker_queue_service import enqueue_repository_pipeline, worker_queue_to_read
from app.ui.deps import get_web_operator, get_web_viewer

router = APIRouter(tags=["UI-Schedules"])

templates = Jinja2Templates(directory="app/templates")


def _parse_repo_id(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


def _parse_status_filter(value: str | None) -> JobScheduleStatus | None:
    if not value:
        return None
    return JobScheduleStatus(value)


def _load_schedule_details(
    session: Session,
    status_filter: JobScheduleStatus | None,
    repo_id: int | None,
) -> list[dict]:
    return list_schedule_details(
        session=session,
        status_filter=status_filter,
        repo_id=repo_id,
    )


@router.get("/schedules", name="schedules")
def schedules(
    request: Request,
    status_filter: str | None = Query(default=None),
    repo_id: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    parsed_status_filter = _parse_status_filter(status_filter)
    parsed_repo_id = _parse_repo_id(repo_id)
    repos = get_all_repos(session)
    schedule_details = _load_schedule_details(
        session=session,
        status_filter=parsed_status_filter,
        repo_id=parsed_repo_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="pages/schedules.html",
        context={
            "page_title": "Schedules",
            "page_name": "schedules",
            "active_page": "schedules",
            "current_user": current_user,
            "repos": repos,
            "schedule_details": schedule_details,
            "status_filter": parsed_status_filter,
            "repo_id": parsed_repo_id,
        },
    )


@router.get("/schedules/table", response_class=HTMLResponse)
def schedules_table(
    request: Request,
    status_filter: str | None = Query(default=None),
    repo_id: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_viewer),
):
    schedule_details = _load_schedule_details(
        session=session,
        status_filter=_parse_status_filter(status_filter),
        repo_id=_parse_repo_id(repo_id),
    )

    return templates.TemplateResponse(
        request=request,
        name="components/schedules_table.html",
        context={
            "current_user": current_user,
            "schedule_details": schedule_details,
        },
    )


@router.post("/schedules/{schedule_id}/run-now", response_class=HTMLResponse)
def run_schedule_now(
    request: Request,
    schedule_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_operator),
):
    try:
        schedule = get_schedule(schedule_id, session)
        job = session.get(Job, schedule.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {schedule.job_id}")

        queue_item = enqueue_repository_pipeline(
            repo_id=job.repo_id,
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
