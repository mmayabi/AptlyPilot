# file: app/services/worker_queue_service.py

from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.job import Job, JobStep, JobStatus
from app.models.script import Script
from app.models.worker_queue import (
    WorkerQueueItem,
    WorkerQueueRequestedBy,
    WorkerQueueStatus,
)
from app.schemas.worker_queue import WorkerQueueRead


def new_execution_id() -> str:
    return str(uuid4())


def worker_queue_to_read(item: WorkerQueueItem) -> WorkerQueueRead:
    return WorkerQueueRead(
        id=item.id,
        job_id=item.job_id,
        job_step_id=item.job_step_id,
        schedule_id=item.schedule_id,
        execution_id=item.execution_id,
        status=item.status,
        requested_by=item.requested_by,
        requested_by_user_id=item.requested_by_user_id,
        run_after=item.run_after,
        attempt_count=item.attempt_count,
        max_attempts=item.max_attempts,
        locked_by=item.locked_by,
        locked_at=item.locked_at,
        heartbeat_at=item.heartbeat_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
        timeout_seconds=item.timeout_seconds,
        error_message=item.error_message,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def get_first_pending_step(job_id: int, session: Session) -> JobStep | None:
    return session.exec(
        select(JobStep)
        .where(
            JobStep.job_id == job_id,
            JobStep.status == JobStatus.PENDING,
        )
        .order_by(JobStep.order, JobStep.id)
    ).first()


def reset_job_steps_for_new_execution(job_id: int, session: Session) -> None:
    """
    چون JobStep در این مدل تعریف ثابت step + آخرین وضعیت است،
    قبل از هر اجرای جدید، stepها reset می‌شوند.
    History کامل اجرای قبلی در worker_queue باقی می‌ماند.
    """
    steps = session.exec(
        select(JobStep).where(JobStep.job_id == job_id)
    ).all()

    for step in steps:
        step.status = JobStatus.PENDING
        step.started_at = None
        step.finished_at = None
        step.log = None
        session.add(step)


def ensure_no_active_queue_for_job(job_id: int, session: Session) -> None:
    existing = session.exec(
        select(WorkerQueueItem).where(
            WorkerQueueItem.job_id == job_id,
            WorkerQueueItem.status.in_(
                [WorkerQueueStatus.QUEUED, WorkerQueueStatus.RUNNING]
            ),
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job already has queued/running worker item: {existing.id}",
        )


def enqueue_job(
    job_id: int,
    session: Session,
    requested_by_user_id: int | None = None,
    requested_by: WorkerQueueRequestedBy = WorkerQueueRequestedBy.MANUAL,
    schedule_id: int | None = None,
    execution_id: str | None = None,
    reset_steps: bool = True,
) -> WorkerQueueItem:
    """
    اجرای Job را شروع نمی‌کند؛ فقط اولین JobStep آماده را وارد worker_queue می‌کند.
    اگر reset_steps=True باشد، قبل از اجرای جدید stepها reset می‌شوند.
    """
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    ensure_no_active_queue_for_job(job_id, session)

    if reset_steps:
        reset_job_steps_for_new_execution(job_id, session)
        session.flush()

    first_step = get_first_pending_step(job_id, session)
    if not first_step:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job has no pending step to enqueue",
        )

    script = session.get(Script, first_step.script_id)
    if not script:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Script not found for step: {first_step.script_id}",
        )

    queue_item = WorkerQueueItem(
        job_id=job.id,
        job_step_id=first_step.id,
        schedule_id=schedule_id,
        execution_id=execution_id or new_execution_id(),
        status=WorkerQueueStatus.QUEUED,
        requested_by=requested_by,
        requested_by_user_id=requested_by_user_id,
        attempt_count=0,
        max_attempts=(script.max_retries or 0) + 1,
        timeout_seconds=script.timeout_seconds or 3600,
    )

    job.status = JobStatus.PENDING
    job.started_at = None
    job.finished_at = None
    job.error_message = None
    job.updated_at = datetime.utcnow()

    session.add(queue_item)
    session.add(job)
    session.commit()
    session.refresh(queue_item)

    return queue_item


def enqueue_next_step_after_success(
    job: Job,
    completed_step: JobStep,
    completed_queue_item: WorkerQueueItem,
    session: Session,
) -> WorkerQueueItem | None:
    """
    بعد از موفقیت یک step، step بعدی همان job را با همان execution_id وارد صف می‌کند.
    """
    next_step = session.exec(
        select(JobStep)
        .where(
            JobStep.job_id == job.id,
            JobStep.status == JobStatus.PENDING,
            JobStep.order > completed_step.order,
        )
        .order_by(JobStep.order, JobStep.id)
    ).first()

    if not next_step:
        job.status = JobStatus.SUCCESS
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        session.add(job)
        return None

    script = session.get(Script, next_step.script_id)
    if not script:
        job.status = JobStatus.FAILED
        job.error_message = f"Script not found for next step: {next_step.script_id}"
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        session.add(job)
        return None

    queue_item = WorkerQueueItem(
        job_id=job.id,
        job_step_id=next_step.id,
        schedule_id=completed_queue_item.schedule_id,
        execution_id=completed_queue_item.execution_id,
        status=WorkerQueueStatus.QUEUED,
        requested_by=WorkerQueueRequestedBy.SYSTEM,
        attempt_count=0,
        max_attempts=(script.max_retries or 0) + 1,
        timeout_seconds=script.timeout_seconds or 3600,
    )

    session.add(queue_item)
    return queue_item


def list_worker_queue(
    session: Session,
    status_filter: WorkerQueueStatus | None = None,
    job_id: int | None = None,
    execution_id: str | None = None,
    schedule_id: int | None = None,
) -> list[WorkerQueueItem]:
    query = select(WorkerQueueItem).order_by(WorkerQueueItem.id)

    if status_filter is not None:
        query = query.where(WorkerQueueItem.status == status_filter)

    if job_id is not None:
        query = query.where(WorkerQueueItem.job_id == job_id)

    if execution_id is not None:
        query = query.where(WorkerQueueItem.execution_id == execution_id)

    if schedule_id is not None:
        query = query.where(WorkerQueueItem.schedule_id == schedule_id)

    return list(session.exec(query).all())