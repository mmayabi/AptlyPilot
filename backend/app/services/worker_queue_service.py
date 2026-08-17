from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.job import Job, JobStep
from app.models.repo import Repo
from app.models.script import Script
from app.models.template import JobTemplate
from app.models.worker_queue import WorkerQueueItem, WorkerQueueRequestedBy, WorkerQueueStatus
from app.schemas.worker_queue import WorkerQueueRead
from app.services.repo_service import ensure_pipeline_job_for_repo

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
        log=item.log,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )

def get_first_step(job_id: int, session: Session) -> JobStep | None:
    return session.exec(
        select(JobStep).where(JobStep.job_id == job_id).order_by(JobStep.order, JobStep.id)
    ).first()

def ensure_no_active_queue_for_job(job_id: int, session: Session) -> None:
    existing = session.exec(
        select(WorkerQueueItem).where(
            WorkerQueueItem.job_id == job_id,
            WorkerQueueItem.status.in_([WorkerQueueStatus.QUEUED, WorkerQueueStatus.RUNNING]),
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
) -> WorkerQueueItem:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job not found: {job_id}")

    ensure_no_active_queue_for_job(job_id, session)

    first_step = get_first_step(job_id, session)
    if not first_step:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job has no steps")

    queue_item = WorkerQueueItem(
        job_id=job.id,
        job_step_id=first_step.id,
        schedule_id=schedule_id,
        execution_id=execution_id or new_execution_id(),
        status=WorkerQueueStatus.QUEUED,
        requested_by=requested_by,
        requested_by_user_id=requested_by_user_id,
        attempt_count=0,
        max_attempts=1,
        timeout_seconds=3600,
    )

    session.add(queue_item)
    session.commit()
    session.refresh(queue_item)
    return queue_item


def enqueue_repository_pipeline(
    repo_id: int,
    session: Session,
    requested_by_user_id: int | None = None,
) -> WorkerQueueItem:
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {repo_id}",
        )

    job = ensure_pipeline_job_for_repo(session, repo)
    session.commit()

    return enqueue_job(
        job_id=job.id,
        session=session,
        requested_by_user_id=requested_by_user_id,
        requested_by=WorkerQueueRequestedBy.MANUAL,
    )


def list_worker_queue_for_repo(
    repo_id: int,
    session: Session,
    limit: int = 20,
) -> list[WorkerQueueItem]:
    jobs = session.exec(select(Job).where(Job.repo_id == repo_id)).all()
    job_ids = [job.id for job in jobs if job.id is not None]

    if not job_ids:
        return []

    return list(
        session.exec(
            select(WorkerQueueItem)
            .where(WorkerQueueItem.job_id.in_(job_ids))
            .order_by(WorkerQueueItem.created_at.desc(), WorkerQueueItem.id.desc())
            .limit(limit)
        ).all()
    )


def list_worker_queue_run_details_for_repo(
    repo_id: int,
    session: Session,
    limit: int = 20,
) -> list[dict]:
    return list_worker_queue_run_details(
        session=session,
        repo_id=repo_id,
        limit=limit,
    )


def list_worker_queue_run_details(
    session: Session,
    status_filter: WorkerQueueStatus | None = None,
    repo_id: int | None = None,
    requested_by: WorkerQueueRequestedBy | None = None,
    limit: int = 50,
) -> list[dict]:
    query = select(WorkerQueueItem).order_by(
        WorkerQueueItem.created_at.desc(),
        WorkerQueueItem.id.desc(),
    )

    if status_filter is not None:
        query = query.where(WorkerQueueItem.status == status_filter)

    if requested_by is not None:
        query = query.where(WorkerQueueItem.requested_by == requested_by)

    if repo_id is not None:
        jobs = session.exec(select(Job).where(Job.repo_id == repo_id)).all()
        job_ids = [job.id for job in jobs if job.id is not None]
        if not job_ids:
            return []
        query = query.where(WorkerQueueItem.job_id.in_(job_ids))

    items = list(session.exec(query.limit(limit)).all())

    step_ids = [item.job_step_id for item in items]
    if not step_ids:
        return []

    steps = session.exec(select(JobStep).where(JobStep.id.in_(step_ids))).all()
    steps_by_id = {step.id: step for step in steps if step.id is not None}

    job_ids = [item.job_id for item in items]
    jobs = session.exec(select(Job).where(Job.id.in_(job_ids))).all()
    jobs_by_id = {job.id: job for job in jobs if job.id is not None}

    repo_ids = [job.repo_id for job in jobs]
    repos = session.exec(select(Repo).where(Repo.id.in_(repo_ids))).all()
    repos_by_id = {repo.id: repo for repo in repos if repo.id is not None}

    script_ids = [step.script_id for step in steps]
    scripts_by_id = {}
    if script_ids:
        scripts = session.exec(select(Script).where(Script.id.in_(script_ids))).all()
        scripts_by_id = {script.id: script for script in scripts if script.id is not None}

    details = []
    for item in items:
        step = steps_by_id.get(item.job_step_id)
        job = jobs_by_id.get(item.job_id)
        repo = repos_by_id.get(job.repo_id) if job else None
        script = scripts_by_id.get(step.script_id) if step else None
        details.append(
            {
                "queue_item": worker_queue_to_read(item),
                "repo_id": repo.id if repo else None,
                "repo_name": repo.name if repo else None,
                "provider": repo.provider if repo else None,
                "release": repo.release if repo else None,
                "step_order": step.order if step else None,
                "script_name": script.name if script else None,
            }
        )

    return details


def get_pipeline_status(items: list[WorkerQueueRead]) -> str:
    statuses = [item.status for item in items]

    if any(status == WorkerQueueStatus.FAILED for status in statuses):
        return WorkerQueueStatus.FAILED
    if any(status == WorkerQueueStatus.RUNNING for status in statuses):
        return WorkerQueueStatus.RUNNING
    if any(status == WorkerQueueStatus.QUEUED for status in statuses):
        return WorkerQueueStatus.QUEUED
    if statuses and all(status == WorkerQueueStatus.SUCCESS for status in statuses):
        return WorkerQueueStatus.SUCCESS
    if statuses and all(status == WorkerQueueStatus.CANCELED for status in statuses):
        return WorkerQueueStatus.CANCELED
    if statuses and all(status == WorkerQueueStatus.SKIPPED for status in statuses):
        return WorkerQueueStatus.SKIPPED

    return "mixed"


def list_worker_pipeline_run_details(
    session: Session,
    status_filter: WorkerQueueStatus | None = None,
    repo_id: int | None = None,
    requested_by: WorkerQueueRequestedBy | None = None,
    limit: int = 50,
) -> list[dict]:
    query = select(WorkerQueueItem).order_by(
        WorkerQueueItem.created_at.desc(),
        WorkerQueueItem.id.desc(),
    )

    if repo_id is not None:
        jobs = session.exec(select(Job).where(Job.repo_id == repo_id)).all()
        job_ids = [job.id for job in jobs if job.id is not None]
        if not job_ids:
            return []
        query = query.where(WorkerQueueItem.job_id.in_(job_ids))

    items = list(session.exec(query.limit(limit * 10)).all())
    if not items:
        return []

    step_ids = [item.job_step_id for item in items]
    steps = session.exec(select(JobStep).where(JobStep.id.in_(step_ids))).all()
    steps_by_id = {step.id: step for step in steps if step.id is not None}

    job_ids = [item.job_id for item in items]
    jobs = session.exec(select(Job).where(Job.id.in_(job_ids))).all()
    jobs_by_id = {job.id: job for job in jobs if job.id is not None}

    template_ids = [job.template_id for job in jobs]
    templates_by_id = {}
    if template_ids:
        templates = session.exec(select(JobTemplate).where(JobTemplate.id.in_(template_ids))).all()
        templates_by_id = {template.id: template for template in templates if template.id is not None}

    repo_ids = [job.repo_id for job in jobs]
    repos = session.exec(select(Repo).where(Repo.id.in_(repo_ids))).all()
    repos_by_id = {repo.id: repo for repo in repos if repo.id is not None}

    script_ids = [step.script_id for step in steps]
    scripts_by_id = {}
    if script_ids:
        scripts = session.exec(select(Script).where(Script.id.in_(script_ids))).all()
        scripts_by_id = {script.id: script for script in scripts if script.id is not None}

    grouped: dict[str, dict] = {}
    for item in items:
        step = steps_by_id.get(item.job_step_id)
        job = jobs_by_id.get(item.job_id)
        repo = repos_by_id.get(job.repo_id) if job else None
        job_template = templates_by_id.get(job.template_id) if job else None
        script = scripts_by_id.get(step.script_id) if step else None

        group = grouped.setdefault(
            item.execution_id,
            {
                "execution_id": item.execution_id,
                "repo_id": repo.id if repo else None,
                "repo_name": repo.name if repo else None,
                "provider": repo.provider if repo else None,
                "release": repo.release if repo else None,
                "job_id": job.id if job else None,
                "template_id": job_template.id if job_template else None,
                "template_name": job_template.name if job_template else None,
                "requested_by": item.requested_by,
                "source_created_at": item.created_at,
                "schedule_id": item.schedule_id,
                "created_at": item.created_at,
                "started_at": item.started_at,
                "finished_at": item.finished_at,
                "steps": [],
            },
        )

        group["created_at"] = min(group["created_at"], item.created_at)
        if item.created_at < group["source_created_at"]:
            group["source_created_at"] = item.created_at
            group["requested_by"] = item.requested_by
            group["schedule_id"] = item.schedule_id
        if item.started_at is not None:
            if group["started_at"] is None or item.started_at < group["started_at"]:
                group["started_at"] = item.started_at
        if item.finished_at is not None:
            if group["finished_at"] is None or item.finished_at > group["finished_at"]:
                group["finished_at"] = item.finished_at

        group["steps"].append(
            {
                "queue_item": worker_queue_to_read(item),
                "step_order": step.order if step else None,
                "script_name": script.name if script else None,
            }
        )

    pipeline_runs = []
    for group in grouped.values():
        group["steps"] = sorted(
            group["steps"],
            key=lambda step: (
                step["step_order"] if step["step_order"] is not None else 999999,
                step["queue_item"].id,
            ),
        )
        group["status"] = get_pipeline_status(
            [step["queue_item"] for step in group["steps"]]
        )

        if status_filter is not None and group["status"] != status_filter:
            continue

        if requested_by is not None and group["requested_by"] != requested_by:
            continue

        pipeline_runs.append(group)

    return sorted(
        pipeline_runs,
        key=lambda run: run["created_at"],
        reverse=True,
    )[:limit]

def enqueue_next_step_after_success(
    job: Job,
    completed_step: JobStep,
    completed_queue_item: WorkerQueueItem,
    session: Session,
) -> WorkerQueueItem | None:
    next_step = session.exec(
        select(JobStep)
        .where(JobStep.job_id == job.id, JobStep.order > completed_step.order)
        .order_by(JobStep.order, JobStep.id)
    ).first()

    if not next_step:
        return None

    queue_item = WorkerQueueItem(
        job_id=job.id,
        job_step_id=next_step.id,
        schedule_id=completed_queue_item.schedule_id,
        execution_id=completed_queue_item.execution_id,
        status=WorkerQueueStatus.QUEUED,
        requested_by=WorkerQueueRequestedBy.SYSTEM,
        attempt_count=0,
        max_attempts=1,
        timeout_seconds=3600,
    )

    session.add(queue_item)
    session.commit()
    return queue_item

def list_worker_queue(
    session: Session,
    status_filter: WorkerQueueStatus | None = None,
    job_id: int | None = None,
    execution_id: str | None = None,
    schedule_id: int | None = None,
    requested_by: WorkerQueueRequestedBy | None = None,
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

    if requested_by is not None:
        query = query.where(WorkerQueueItem.requested_by == requested_by)

    return list(session.exec(query).all())
