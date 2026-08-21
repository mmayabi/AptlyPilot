import json
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.clients.aptly_client import AptlyClient
from app.models.job import Job, JobStep
from app.models.script import Script
from app.models.worker_queue import WorkerQueueItem, WorkerQueueStatus
from app.services.app_setting_service import make_aptly_client_from_settings
from app.services.repository_operation_service import (
    SUPPORTED_REPOSITORY_OPERATION_SCRIPTS,
    run_repository_operation_step,
)
from app.services.worker_queue_service import enqueue_next_step_after_success

HEARTBEAT_INTERVAL_SECONDS = 30
STALE_HEARTBEAT_SECONDS = 300

def pick_next_queue_item(session: Session) -> WorkerQueueItem | None:
    running = session.exec(
        select(WorkerQueueItem).where(WorkerQueueItem.status == WorkerQueueStatus.RUNNING)
    ).first()

    if running:
        return None

    now = datetime.utcnow()
    return session.exec(
        select(WorkerQueueItem)
        .where(
            WorkerQueueItem.status == WorkerQueueStatus.QUEUED,
            (WorkerQueueItem.run_after == None) | (WorkerQueueItem.run_after <= now),
        )
        .order_by(WorkerQueueItem.id)
    ).first()

def mark_queue_item_running(item: WorkerQueueItem, worker_id: str, session: Session) -> None:
    now = datetime.utcnow()
    item.status = WorkerQueueStatus.RUNNING
    item.locked_by = worker_id
    item.locked_at = now
    item.heartbeat_at = now
    item.started_at = now
    item.updated_at = now
    item.attempt_count += 1

    session.add(item)
    session.commit()

def mark_step_success(item: WorkerQueueItem, log: str, session: Session) -> None:
    now = datetime.utcnow()
    session.refresh(item)
    if item.status == WorkerQueueStatus.CANCELED:
        item.log = item.log or log
        item.finished_at = item.finished_at or now
        item.updated_at = now
        session.add(item)
        session.commit()
        return

    item.status = WorkerQueueStatus.SUCCESS
    item.finished_at = now
    item.log = log
    item.updated_at = now
    session.add(item)

    step = session.get(JobStep, item.job_step_id)
    if step:
        session.add(step)  # فقط برای ارتباط، runtime حذف شده
    job = session.get(Job, item.job_id)
    if job:
        session.add(job)

    session.commit()
    if job and step:
        enqueue_next_step_after_success(job, step, item, session)

def mark_step_failed(item: WorkerQueueItem, log: str, error_message: str, session: Session, retry_allowed: bool):
    now = datetime.utcnow()
    session.refresh(item)
    if item.status == WorkerQueueStatus.CANCELED:
        item.log = item.log or log
        item.finished_at = item.finished_at or now
        item.updated_at = now
        session.add(item)
        session.commit()
        return

    if retry_allowed and item.attempt_count < item.max_attempts:
        item.status = WorkerQueueStatus.QUEUED
        item.run_after = now + timedelta(seconds=300)
        item.error_message = error_message
        item.started_at = None
        item.finished_at = None
    else:
        item.status = WorkerQueueStatus.FAILED
        item.finished_at = now
        item.error_message = error_message

    item.log = log
    item.updated_at = now
    session.add(item)
    session.commit()


def make_aptly_client() -> AptlyClient:
    return make_aptly_client_from_settings()


def json_log(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def run_script_step(
    *,
    script: Script,
    job: Job,
    step: JobStep,
    session: Session,
) -> dict[str, Any]:
    params = step.params or {}

    if script.name in SUPPORTED_REPOSITORY_OPERATION_SCRIPTS:
        return run_repository_operation_step(
            script_name=script.name,
            session=session,
            repo_id=job.repo_id,
            params=params,
            aptly_client=make_aptly_client(),
        )

    raise ValueError(
        f"Unsupported script '{script.name}'. "
        "Only Aptly operation scripts are executable by this worker."
    )


def run_queue_item(item: WorkerQueueItem, session: Session, worker_id: str = "worker-1") -> WorkerQueueItem:
    mark_queue_item_running(item, worker_id, session)

    job = session.get(Job, item.job_id)
    if not job:
        mark_step_failed(
            item=item,
            log="",
            error_message=f"Job not found: {item.job_id}",
            session=session,
            retry_allowed=False,
        )
        return session.get(WorkerQueueItem, item.id)

    step = session.get(JobStep, item.job_step_id)
    if not step:
        mark_step_failed(
            item=item,
            log="",
            error_message=f"JobStep not found: {item.job_step_id}",
            session=session,
            retry_allowed=False,
        )
        return session.get(WorkerQueueItem, item.id)

    script = session.get(Script, step.script_id)
    if not script:
        mark_step_failed(item, "", f"Script not found: {step.script_id}", session, retry_allowed=False)
        return session.get(WorkerQueueItem, item.id)

    try:
        result = run_script_step(
            script=script,
            job=job,
            step=step,
            session=session,
        )
        mark_step_success(
            item=item,
            log=json_log(result),
            session=session,
        )
    except Exception as exc:
        failure_log = {
            "status": "failed",
            "script_name": script.name,
            "job_id": job.id,
            "job_step_id": step.id,
            "repo_id": job.repo_id,
            "error": str(exc),
        }

        mark_step_failed(
            item=item,
            log=json_log(failure_log),
            error_message=str(exc),
            session=session,
            retry_allowed=True,
        )

    return session.get(WorkerQueueItem, item.id)

def run_once(session: Session, worker_id: str = "worker-1") -> WorkerQueueItem | None:
    item = pick_next_queue_item(session)
    if not item:
        return None
    return run_queue_item(item, session, worker_id=worker_id)

def recover_stale_running_items(session: Session) -> int:
    threshold = datetime.utcnow() - timedelta(seconds=STALE_HEARTBEAT_SECONDS)
    stale_items = session.exec(
        select(WorkerQueueItem).where(
            WorkerQueueItem.status == WorkerQueueStatus.RUNNING,
            WorkerQueueItem.heartbeat_at < threshold
        )
    ).all()
    for item in stale_items:
        item.status = WorkerQueueStatus.FAILED
        item.finished_at = datetime.utcnow()
        item.error_message = "Worker heartbeat stale"
        item.updated_at = datetime.utcnow()
        session.add(item)
    session.commit()
    return len(stale_items)
