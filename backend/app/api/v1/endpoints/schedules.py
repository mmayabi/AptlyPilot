# file: app/api/v1/endpoints/schedules.py

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_db_session
from app.core.permissions import require_admin, require_operator, require_viewer
from app.models.user import User
from app.services.scheduler_service import process_due_schedules
from app.schemas.job_schedule import (
    JobScheduleCreate,
    JobScheduleRead,
    JobScheduleUpdate,
)
from app.services.job_schedule_service import (
    create_schedule,
    delete_schedule,
    disable_schedule,
    enable_schedule,
    get_schedule,
    list_schedules,
    schedule_to_read,
    update_schedule,
)

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.post("", response_model=JobScheduleRead)
def create_schedule_endpoint(
    schedule_in: JobScheduleCreate,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    schedule = create_schedule(
        schedule_in=schedule_in,
        session=session,
        created_by_user_id=current_user.id,
    )
    return schedule_to_read(schedule)


@router.get("", response_model=list[JobScheduleRead])
def list_schedules_endpoint(
    job_id: int | None = None,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    schedules = list_schedules(session=session, job_id=job_id)
    return [schedule_to_read(schedule) for schedule in schedules]


@router.get("/{schedule_id}", response_model=JobScheduleRead)
def get_schedule_endpoint(
    schedule_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    schedule = get_schedule(schedule_id, session)
    return schedule_to_read(schedule)


@router.put("/{schedule_id}", response_model=JobScheduleRead)
def update_schedule_endpoint(
    schedule_id: int,
    schedule_in: JobScheduleUpdate,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    schedule = update_schedule(
        schedule_id=schedule_id,
        schedule_in=schedule_in,
        session=session,
    )
    return schedule_to_read(schedule)


@router.delete("/{schedule_id}")
def delete_schedule_endpoint(
    schedule_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    delete_schedule(schedule_id, session)
    return {"detail": "Schedule deleted successfully."}


@router.post("/{schedule_id}/enable", response_model=JobScheduleRead)
def enable_schedule_endpoint(
    schedule_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    schedule = enable_schedule(schedule_id, session)
    return schedule_to_read(schedule)


@router.post("/{schedule_id}/disable", response_model=JobScheduleRead)
def disable_schedule_endpoint(
    schedule_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    schedule = disable_schedule(schedule_id, session)
    return schedule_to_read(schedule)

@router.post("/test_scheduler")
def test_scheduler(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    processed = process_due_schedules(session)
    return {"processed": processed}