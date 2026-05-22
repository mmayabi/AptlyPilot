from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.job import Job, JobStep, JobStatus, JobTriggerType, ScheduleType
from app.models.template import JobTemplate, JobStepTemplate
from app.schemas.job import JobCreate, JobUpdate, JobRead, JobStepRead

# -----------------------------
# Helpers / Validation
# -----------------------------
def check_template_exists(template_id: int, session: Session) -> JobTemplate:
    template = session.get(JobTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template id {template_id} not found")
    return template

def check_running_job(job_id: int, session: Session):
    job = session.get(Job, job_id)
    if job and job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Job is currently running and cannot be modified")

def check_script_exists(script_id: int, session: Session):
    if not session.get(Script, script_id):
        raise HTTPException(status_code=400, detail=f"Script id {script_id} does not exist")

def get_step_or_404(step_id: int, session: Session) -> JobStep:
    step = session.get(JobStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail=f"JobStep id {step_id} not found")
    return step

# -----------------------------
# mapper
# -----------------------------
def job_to_read(job: Job, session: Session) -> JobRead:
    """
    تبدیل مدل دیتابیس Job به schema خروجی JobRead.
    این تابع باعث می‌شود همه endpointها response یکسان و کامل داشته باشند.
    """
    steps = session.exec(
        select(JobStep)
        .where(JobStep.job_id == job.id)
        .order_by(JobStep.order)
    ).all()

    return JobRead(
        id=job.id,
        template_id=job.template_id,
        repo_id=job.repo_id,
        status=job.status,
        trigger_type=job.trigger_type,
        scheduled=job.scheduled,
        run_at=job.run_at,
        schedule_type=job.schedule_type,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
        steps=[
            JobStepRead(
                id=step.id,
                script_id=step.script_id,
                order=step.order,
                params=step.params or {},
                status=step.status,
                started_at=step.started_at,
                finished_at=step.finished_at,
                log=step.log,
            )
            for step in steps
        ],
    )

# -----------------------------
# CRUD Job
# -----------------------------
def create_job(job_in: JobCreate, session: Session) -> Job:
    template = check_template_exists(job_in.template_id, session)

    scheduled = job_in.schedule_type != ScheduleType.MANUAL

    job = Job(
        template_id=template.id,
        repo_id=job_in.repo_id,
        status=JobStatus.PENDING,
        trigger_type=job_in.trigger_type,
        scheduled=scheduled,
        run_at=job_in.run_at,
        schedule_type=job_in.schedule_type,
    )

    session.add(job)
    session.commit()
    session.refresh(job)

    template_steps = session.exec(
        select(JobStepTemplate)
        .where(JobStepTemplate.template_id == template.id)
        .order_by(JobStepTemplate.order)
    ).all()

    for index, template_step in enumerate(template_steps):
        params = job_in.params[index] if index < len(job_in.params) else {}

        job_step = JobStep(
            job_id=job.id,
            step_template_id=template_step.id,
            script_id=template_step.script_id,
            order=template_step.order,
            params=params,
            status=JobStatus.PENDING,
        )
        session.add(job_step)

    session.commit()
    session.refresh(job)

    return job

def update_job(job_id: int, job_in: JobUpdate, session: Session) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    check_running_job(job_id, session)

    if job_in.run_at is not None:
        job.run_at = job_in.run_at

    if job_in.trigger_type is not None:
        job.trigger_type = job_in.trigger_type

    if job_in.schedule_type is not None:
        job.schedule_type = job_in.schedule_type
        job.scheduled = job_in.schedule_type != ScheduleType.MANUAL

    job.updated_at = datetime.utcnow()

    session.add(job)
    session.commit()
    session.refresh(job)

    return job

def delete_job(job_id: int, session: Session) -> None:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == JobStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a running job",
        )

    job_steps = session.exec(
        select(JobStep).where(JobStep.job_id == job_id)
    ).all()

    for step in job_steps:
        session.delete(step)

    # مهم: حذف stepها را قبل از حذف job به دیتابیس flush کن
    session.flush()

    session.delete(job)
    session.commit()

def list_jobs(session: Session, template_id: Optional[int] = None) -> List[Job]:
    query = select(Job)
    if template_id:
        query = query.where(Job.template_id == template_id)
    return session.exec(query).all()

def get_job(job_id: int, session: Session) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job