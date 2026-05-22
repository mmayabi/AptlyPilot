# file: app/services/worker_service.py

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.config import get_settings
from app.models.job import Job, JobStep, JobStatus
from app.models.script import Script
from app.models.worker_queue import WorkerQueueItem, WorkerQueueStatus
from app.services.worker_queue_service import enqueue_next_step_after_success

settings = get_settings()

HEARTBEAT_INTERVAL_SECONDS = 30
STALE_HEARTBEAT_SECONDS = 300


def get_scripts_dir() -> Path:
    """
    اگر در config مسیر scripts داری، از آن استفاده کن.
    اگر نداری، مسیر پیش‌فرض app/scripts در نظر گرفته می‌شود.
    """
    scripts_dir = getattr(settings, "SCRIPTS_DIR", None)

    if scripts_dir:
        return Path(scripts_dir)

    return Path(__file__).resolve().parents[1] / "scripts"


def pick_next_queue_item(session: Session) -> WorkerQueueItem | None:
    """
    چون اجرای موازی نداریم:
    اگر item در حال اجرا وجود داشته باشد، هیچ item جدیدی انتخاب نمی‌شود.
    """
    running = session.exec(
        select(WorkerQueueItem).where(
            WorkerQueueItem.status == WorkerQueueStatus.RUNNING
        )
    ).first()

    if running:
        return None

    now = datetime.utcnow()

    return session.exec(
        select(WorkerQueueItem)
        .where(WorkerQueueItem.status == WorkerQueueStatus.QUEUED)
        .where(
            (WorkerQueueItem.run_after == None) |  # noqa: E711
            (WorkerQueueItem.run_after <= now)
        )
        .order_by(WorkerQueueItem.id)
    ).first()


def mark_queue_item_running(
    item: WorkerQueueItem,
    worker_id: str,
    session: Session,
) -> None:
    now = datetime.utcnow()

    item.status = WorkerQueueStatus.RUNNING
    item.locked_by = worker_id
    item.locked_at = now
    item.heartbeat_at = now
    item.started_at = now
    item.updated_at = now
    item.attempt_count += 1

    job = session.get(Job, item.job_id)
    step = session.get(JobStep, item.job_step_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {item.job_id}")

    if not step:
        raise HTTPException(status_code=404, detail=f"JobStep not found: {item.job_step_id}")

    job.status = JobStatus.RUNNING
    job.started_at = job.started_at or now
    job.updated_at = now

    step.status = JobStatus.RUNNING
    step.started_at = now

    session.add(item)
    session.add(job)
    session.add(step)
    session.commit()


def update_heartbeat(item_id: int, session: Session) -> None:
    item = session.get(WorkerQueueItem, item_id)
    if not item:
        return

    item.heartbeat_at = datetime.utcnow()
    item.updated_at = datetime.utcnow()
    session.add(item)
    session.commit()


def build_script_command(script: Script, params_file: str) -> list[str]:
    scripts_dir = get_scripts_dir()
    script_path = scripts_dir / script.name

    if not script_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Script file not found: {script_path}",
        )

    return [
        sys.executable,
        str(script_path),
        "--params-file",
        params_file,
    ]


def run_script_subprocess(
    script: Script,
    params: dict,
    queue_item: WorkerQueueItem,
    session: Session,
) -> tuple[int, str]:
    """
    خروجی:
      exit_code, combined_log
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(params or {}, f)
        params_file = f.name

    command = build_script_command(script, params_file)

    started_at = time.time()
    output_lines: list[str] = []

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

        last_heartbeat = 0.0

        while True:
            exit_code = process.poll()

            if exit_code is not None:
                if process.stdout:
                    remaining = process.stdout.read()
                    if remaining:
                        output_lines.append(remaining)
                return exit_code, "".join(output_lines)

            elapsed = time.time() - started_at

            if elapsed > queue_item.timeout_seconds:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    time.sleep(3)
                    if process.poll() is None:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass

                output_lines.append(
                    f"\nTimeout after {queue_item.timeout_seconds} seconds\n"
                )
                return 124, "".join(output_lines)

            now = time.time()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                update_heartbeat(queue_item.id, session)
                last_heartbeat = now

            if process.stdout:
                line = process.stdout.readline()
                if line:
                    output_lines.append(line)

            time.sleep(1)

    finally:
        try:
            os.unlink(params_file)
        except FileNotFoundError:
            pass


def mark_step_success(
    item: WorkerQueueItem,
    log: str,
    session: Session,
) -> None:
    now = datetime.utcnow()

    job = session.get(Job, item.job_id)
    step = session.get(JobStep, item.job_step_id)

    if not job or not step:
        raise RuntimeError("Job or JobStep not found while marking success")

    item.status = WorkerQueueStatus.SUCCESS
    item.finished_at = now
    item.updated_at = now
    item.error_message = None

    step.status = JobStatus.SUCCESS
    step.finished_at = now
    step.log = log

    session.add(item)
    session.add(step)

    enqueue_next_step_after_success(
        job=job,
        completed_step=step,
        completed_queue_item=item,
        session=session,
    )

    session.commit()

def mark_step_failed(
    item: WorkerQueueItem,
    log: str,
    error_message: str,
    session: Session,
    retry_allowed: bool,
) -> None:
    now = datetime.utcnow()

    job = session.get(Job, item.job_id)
    step = session.get(JobStep, item.job_step_id)

    if not job or not step:
        raise RuntimeError("Job or JobStep not found while marking failure")

    if retry_allowed and item.attempt_count < item.max_attempts:
        item.status = WorkerQueueStatus.QUEUED
        item.run_after = now + timedelta(seconds=300)
        item.error_message = error_message
        item.locked_by = None
        item.locked_at = None
        item.heartbeat_at = None
        item.started_at = None
        item.updated_at = now

        step.status = JobStatus.PENDING
        step.log = log

        session.add(item)
        session.add(step)
        session.commit()
        return

    item.status = WorkerQueueStatus.FAILED
    item.finished_at = now
    item.updated_at = now
    item.error_message = error_message

    step.status = JobStatus.FAILED
    step.finished_at = now
    step.log = log

    job.status = JobStatus.FAILED
    job.finished_at = now
    job.error_message = error_message
    job.updated_at = now

    # stepهای بعدی را skipped کن
    next_steps = session.exec(
        select(JobStep).where(
            JobStep.job_id == job.id,
            JobStep.status == JobStatus.PENDING,
            JobStep.order > step.order,
        )
    ).all()

    for next_step in next_steps:
        next_step.status = JobStatus.SKIPPED
        next_step.finished_at = now
        session.add(next_step)

    session.add(item)
    session.add(step)
    session.add(job)
    session.commit()


def run_queue_item(
    item: WorkerQueueItem,
    session: Session,
    worker_id: str = "worker-1",
) -> WorkerQueueItem:
    mark_queue_item_running(item, worker_id, session)

    # refresh بعد از تغییر status
    item = session.get(WorkerQueueItem, item.id)
    step = session.get(JobStep, item.job_step_id)

    if not step:
        raise HTTPException(status_code=404, detail="JobStep not found")

    script = session.get(Script, step.script_id)
    if not script:
        mark_step_failed(
            item=item,
            log="",
            error_message=f"Script not found: {step.script_id}",
            session=session,
            retry_allowed=False,
        )
        return session.get(WorkerQueueItem, item.id)

    exit_code, log = run_script_subprocess(
        script=script,
        params=step.params or {},
        queue_item=item,
        session=session,
    )

    if exit_code == 0:
        mark_step_success(item, log, session)
    else:
        is_timeout = exit_code == 124
        retry_allowed = bool(script.retry_on_timeout) if is_timeout else True

        error_message = (
            f"Step timeout after {item.timeout_seconds} seconds"
            if is_timeout
            else f"Script failed with exit code {exit_code}"
        )

        # retry delay از script
        item.timeout_seconds = script.timeout_seconds or item.timeout_seconds

        mark_step_failed(
            item=item,
            log=log,
            error_message=error_message,
            session=session,
            retry_allowed=retry_allowed,
        )

    return session.get(WorkerQueueItem, item.id)


def run_once(session: Session, worker_id: str = "worker-1") -> WorkerQueueItem | None:
    """
    فقط یک queue item را اجرا می‌کند.
    برای تست endpoint عالی است.
    """
    item = pick_next_queue_item(session)
    if not item:
        return None

    return run_queue_item(item, session, worker_id=worker_id)


def recover_stale_running_items(session: Session) -> int:
    """
    اگر Worker کرش کند، itemهای running با heartbeat قدیمی را failed می‌کند.
    فعلاً retry_on_worker_lost را خودکار انجام نمی‌دهیم.
    """
    threshold = datetime.utcnow() - timedelta(seconds=STALE_HEARTBEAT_SECONDS)

    stale_items = session.exec(
        select(WorkerQueueItem).where(
            WorkerQueueItem.status == WorkerQueueStatus.RUNNING,
            WorkerQueueItem.heartbeat_at < threshold,
        )
    ).all()

    count = 0

    for item in stale_items:
        job = session.get(Job, item.job_id)
        step = session.get(JobStep, item.job_step_id)

        now = datetime.utcnow()
        error_message = "Worker heartbeat stale"

        item.status = WorkerQueueStatus.FAILED
        item.finished_at = now
        item.error_message = error_message
        item.updated_at = now

        if step:
            step.status = JobStatus.FAILED
            step.finished_at = now
            step.log = error_message
            session.add(step)

        if job:
            job.status = JobStatus.FAILED
            job.finished_at = now
            job.error_message = error_message
            job.updated_at = now
            session.add(job)

        session.add(item)
        count += 1

    session.commit()
    return count