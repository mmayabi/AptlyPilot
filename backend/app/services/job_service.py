from datetime import datetime, UTC
from sqlmodel import Session, select
from app.models.job import Job, JobAction, JobStatus
from app.models.job_step import JobStep

def create_job(session: Session, repo_id: int, steps: list[dict], trigger_type: str = "manual", triggered_by_user_id: int | None = None) -> Job:
    job = Job(
        repo_id=repo_id,
        action=JobAction.FULL_SYNC,
        status=JobStatus.PENDING,
        trigger_type=trigger_type,
        triggered_by_user_id=triggered_by_user_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    # ایجاد JobStep از template
    for step in steps:
        step_obj = JobStep(
            job_id=job.id,
            name=step.get("name", "step"),
            type=step.get("type", "command"),
            command=step.get("command"),
            action=step.get("action"),
            params=step.get("params", {}),
            status=JobStatus.PENDING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)
        )
        session.add(step_obj)
    session.commit()
    return job

def list_jobs(session: Session):
    statement = select(Job).order_by(Job.created_at.desc())
    return session.exec(statement).all()

def get_job(session: Session, job_id: int):
    return session.get(Job, job_id)

def get_job_steps(session: Session, job_id: int):
    statement = select(JobStep).where(JobStep.job_id == job_id).order_by(JobStep.id)
    return session.exec(statement).all()

def retry_job(session: Session, job_id: int):
    job = session.get(Job, job_id)
    if not job:
        return None
    job.status = JobStatus.PENDING
    session.add(job)
    statement = select(JobStep).where(JobStep.job_id == job.id)
    steps = session.exec(statement).all()
    for step in steps:
        if step.status in [JobStatus.FAILED, JobStatus.CANCELED]:
            step.status = JobStatus.PENDING
            step.stdout = None
            step.stderr = None
            step.exit_code = None
            session.add(step)
    session.commit()
    session.refresh(job)
    return job

def cancel_job(session: Session, job_id: int):
    job = session.get(Job, job_id)
    if not job:
        return None
    job.status = JobStatus.CANCELED
    session.add(job)
    statement = select(JobStep).where(JobStep.job_id == job.id)
    steps = session.exec(statement).all()
    for step in steps:
        if step.status in [JobStatus.PENDING, JobStatus.RUNNING]:
            step.status = JobStatus.CANCELED
            session.add(step)
    session.commit()
    session.refresh(job)
    return job