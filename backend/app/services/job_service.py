from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.job import Job, JobStep, JobDefinitionStatus
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

def get_step_or_404(step_id: int, session: Session) -> JobStep:
    step = session.get(JobStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail=f"JobStep id {step_id} not found")
    return step

# -----------------------------
# Mapper
# -----------------------------
def job_to_read(job: Job, session: Session) -> JobRead:
    steps = session.exec(
        select(JobStep).where(JobStep.job_id == job.id).order_by(JobStep.order)
    ).all()

    return JobRead(
        id=job.id,
        template_id=job.template_id,
        repo_id=job.repo_id,
        status=job.status,
        created_by_user_id=job.created_by_user_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        steps=[
            JobStepRead(
                id=step.id,
                script_id=step.script_id,
                order=step.order,
                params=step.params or {},
            )
            for step in steps
        ],
    )

# -----------------------------
# CRUD Job
# -----------------------------
def create_job(job_in: JobCreate, session: Session) -> Job:
    template = check_template_exists(job_in.template_id, session)

    job = Job(
        template_id=template.id,
        repo_id=job_in.repo_id,
        status=JobDefinitionStatus.ACTIVE,
        created_by_user_id=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
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
        )
        session.add(job_step)

    session.commit()
    session.refresh(job)

    return job

def update_job(job_id: int, job_in: JobUpdate, session: Session) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.updated_at = datetime.utcnow()
    if job_in.status:
        job.status = job_in.status

    session.add(job)
    session.commit()
    session.refresh(job)

    return job

def delete_job(job_id: int, session: Session) -> None:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_steps = session.exec(select(JobStep).where(JobStep.job_id == job_id)).all()
    for step in job_steps:
        session.delete(step)

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