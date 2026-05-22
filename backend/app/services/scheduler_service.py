# file: app/services/scheduler_service.py

import calendar
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.models.job_schedule import (
    JobSchedule,
    JobScheduleStatus,
    JobScheduleType,
)
from app.models.worker_queue import (
    WorkerQueueItem,
    WorkerQueueRequestedBy,
    WorkerQueueStatus,
)
from app.services.worker_queue_service import enqueue_job, new_execution_id


def add_one_month(dt: datetime) -> datetime:
    year = dt.year
    month = dt.month + 1

    if month > 12:
        month = 1
        year += 1

    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)

    return dt.replace(year=year, month=month, day=day)


def compute_next_run_at(current_run_at: datetime, schedule_type: JobScheduleType) -> datetime | None:
    if schedule_type == JobScheduleType.ONCE:
        return None

    if schedule_type == JobScheduleType.DAILY:
        return current_run_at + timedelta(days=1)

    if schedule_type == JobScheduleType.WEEKLY:
        return current_run_at + timedelta(weeks=1)

    if schedule_type == JobScheduleType.MONTHLY:
        return add_one_month(current_run_at)

    return None


def has_active_queue_for_job(job_id: int, session: Session) -> bool:
    active = session.exec(
        select(WorkerQueueItem).where(
            WorkerQueueItem.job_id == job_id,
            WorkerQueueItem.status.in_(
                [WorkerQueueStatus.QUEUED, WorkerQueueStatus.RUNNING]
            ),
        )
    ).first()

    return active is not None


def get_due_schedules(session: Session, limit: int = 20) -> list[JobSchedule]:
    now = datetime.utcnow()

    return list(
        session.exec(
            select(JobSchedule)
            .where(JobSchedule.status == JobScheduleStatus.ENABLED)
            .where(JobSchedule.next_run_at <= now)
            .order_by(JobSchedule.next_run_at, JobSchedule.id)
            .limit(limit)
        ).all()
    )


def process_due_schedules(session: Session, limit: int = 20) -> int:
    """
    Scheduler run-once:
    - scheduleهای due را پیدا می‌کند
    - اگر job آن‌ها active queue نداشته باشد، step اول job را enqueue می‌کند
    - schedule.next_run_at را جلو می‌برد
    """
    due_schedules = get_due_schedules(session, limit=limit)
    processed = 0

    for schedule in due_schedules:
        if has_active_queue_for_job(schedule.job_id, session):
            # اجرای قبلی همین job هنوز در صف/در حال اجراست.
            # فعلاً زمان‌بندی را جلو نمی‌بریم تا اجرا از دست نرود.
            continue

        current_run_at = schedule.next_run_at
        execution_id = new_execution_id()

        enqueue_job(
            job_id=schedule.job_id,
            session=session,
            requested_by_user_id=None,
            requested_by=WorkerQueueRequestedBy.SCHEDULER,
            schedule_id=schedule.id,
            execution_id=execution_id,
            reset_steps=True,
        )

        schedule.last_run_at = current_run_at

        next_run_at = compute_next_run_at(
            current_run_at=current_run_at,
            schedule_type=schedule.schedule_type,
        )

        if next_run_at is None:
            schedule.status = JobScheduleStatus.DISABLED
        else:
            schedule.next_run_at = next_run_at

        schedule.updated_at = datetime.utcnow()

        session.add(schedule)
        session.commit()

        processed += 1

    return processed