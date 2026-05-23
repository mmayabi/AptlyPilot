# file: app/services/job_schedule_service.py

from datetime import datetime

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.worker_queue import WorkerQueueItem
from app.models.job import Job
from app.models.job_schedule import JobSchedule, JobScheduleStatus
from app.schemas.job_schedule import JobScheduleCreate, JobScheduleRead, JobScheduleUpdate


def schedule_to_read(schedule: JobSchedule) -> JobScheduleRead:
    return JobScheduleRead(
        id=schedule.id,
        job_id=schedule.job_id,
        schedule_type=schedule.schedule_type,
        status=schedule.status,
        next_run_at=schedule.next_run_at,
        last_run_at=schedule.last_run_at,
        created_by_user_id=schedule.created_by_user_id,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


def get_schedule(schedule_id: int, session: Session) -> JobSchedule:
    schedule = session.get(JobSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule not found: {schedule_id}")
    return schedule


def list_schedules(session: Session, job_id: int | None = None) -> list[JobSchedule]:
    query = select(JobSchedule).order_by(JobSchedule.id)
    if job_id is not None:
        query = query.where(JobSchedule.job_id == job_id)
    return list(session.exec(query).all())


def create_schedule(schedule_in: JobScheduleCreate, session: Session, created_by_user_id: int | None = None) -> JobSchedule:
    job = session.get(Job, schedule_in.job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job not found: {schedule_in.job_id}")

    schedule = JobSchedule(
        job_id=schedule_in.job_id,
        schedule_type=schedule_in.schedule_type,
        status=JobScheduleStatus.ENABLED,
        next_run_at=schedule_in.next_run_at,
        created_by_user_id=created_by_user_id,
    )

    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


def update_schedule(schedule_id: int, schedule_in: JobScheduleUpdate, session: Session) -> JobSchedule:
    schedule = get_schedule(schedule_id, session)
    if schedule_in.schedule_type is not None:
        schedule.schedule_type = schedule_in.schedule_type
    if schedule_in.status is not None:
        schedule.status = schedule_in.status
    if schedule_in.next_run_at is not None:
        schedule.next_run_at = schedule_in.next_run_at

    schedule.updated_at = datetime.utcnow()
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


def delete_schedule(schedule_id: int, session: Session) -> None:
    schedule = get_schedule(schedule_id, session)

    # اگر در WorkerQueue execution history دارد، خطای مناسب بده
    has_worker_history = session.exec(
        select(WorkerQueueItem).where(WorkerQueueItem.schedule_id == schedule_id)
    ).first()

    if has_worker_history:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete schedule because it has worker execution history. Disable the schedule instead."
        )

    session.delete(schedule)
    session.commit()


def enable_schedule(schedule_id: int, session: Session) -> JobSchedule:
    schedule = get_schedule(schedule_id, session)
    schedule.status = JobScheduleStatus.ENABLED
    schedule.updated_at = datetime.utcnow()
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


def disable_schedule(schedule_id: int, session: Session) -> JobSchedule:
    schedule = get_schedule(schedule_id, session)
    schedule.status = JobScheduleStatus.DISABLED
    schedule.updated_at = datetime.utcnow()
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule