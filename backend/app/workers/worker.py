import time
import subprocess
import requests
from datetime import datetime, UTC

from sqlmodel import Session, select
from app.db.session import engine
from app.models.job import Job, JobStatus
from app.models.job_step import JobStep

# -------------------------------------
# Config برای Aptly API
# -------------------------------------
APTLY_BASE_URL = "http://localhost:8080/api"  # تغییر دهید به URL واقعی
APTLY_API_KEY = "your_api_key_here"
APTLY_TIMEOUT = 30

# زمان sleep بین polling دیتابیس
SLEEP_INTERVAL = 5


# -------------------------------------
# اجرای Stepهای command
# -------------------------------------
def run_command_step(step: JobStep):
    try:
        result = subprocess.run(step.command, shell=True, capture_output=True, text=True)
        step.stdout = result.stdout
        step.stderr = result.stderr
        step.exit_code = result.returncode
        step.status = JobStatus.SUCCESS if result.returncode == 0 else JobStatus.FAILED
    except Exception as e:
        step.stderr = str(e)
        step.status = JobStatus.FAILED
        step.exit_code = -1
    finally:
        step.finished_at = datetime.now(UTC)


# -------------------------------------
# اجرای Stepهای API
# -------------------------------------
def run_api_step(step: JobStep):
    try:
        url = f"{APTLY_BASE_URL}/{step.action}"
        headers = {
            "Authorization": f"Bearer {APTLY_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = step.params or {}
        response = requests.post(url, headers=headers, json=payload, timeout=APTLY_TIMEOUT)

        step.stdout = response.text
        step.stderr = None if response.status_code < 400 else response.text
        step.exit_code = response.status_code
        step.status = JobStatus.SUCCESS if response.status_code < 400 else JobStatus.FAILED
    except Exception as e:
        step.stderr = str(e)
        step.exit_code = -1
        step.status = JobStatus.FAILED
    finally:
        step.finished_at = datetime.now(UTC)


# -------------------------------------
# اجرای یک Step با انتخاب نوع
# -------------------------------------
def execute_step(session: Session, step: JobStep):
    step.status = JobStatus.RUNNING
    step.started_at = datetime.now(UTC)
    session.add(step)
    session.commit()
    session.refresh(step)

    if step.type == "command" and step.command:
        run_command_step(step)
    elif step.type == "api" and step.action:
        run_api_step(step)
    else:
        step.stderr = "Invalid step configuration"
        step.status = JobStatus.FAILED
        step.exit_code = -1
        step.finished_at = datetime.now(UTC)

    session.add(step)
    session.commit()


# -------------------------------------
# اجرای یک Job کامل
# -------------------------------------
def execute_job(session: Session, job: Job):
    job.status = JobStatus.RUNNING
    session.add(job)
    session.commit()
    session.refresh(job)

    steps = session.exec(select(JobStep).where(JobStep.job_id == job.id).order_by(JobStep.id)).all()
    for step in steps:
        if step.status in [JobStatus.PENDING, JobStatus.FAILED]:
            execute_step(session, step)
            if step.status == JobStatus.FAILED:
                job.status = JobStatus.FAILED
                session.add(job)
                session.commit()
                return

    steps = session.exec(select(JobStep).where(JobStep.job_id == job.id)).all()
    if all(s.status == JobStatus.SUCCESS for s in steps):
        job.status = JobStatus.SUCCESS
    session.add(job)
    session.commit()


# -------------------------------------
# Worker اصلی با polling و sleep
# -------------------------------------
def run_worker():
    print("Worker started, polling jobs every", SLEEP_INTERVAL, "seconds...")
    while True:
        with Session(engine) as session:
            pending_jobs = session.exec(select(Job).where(Job.status == JobStatus.PENDING).order_by(Job.created_at)).all()
            for job in pending_jobs:
                print(f"Executing Job {job.id} for repo {job.repo_id}")
                execute_job(session, job)
        time.sleep(SLEEP_INTERVAL)


if __name__ == "__main__":
    run_worker()