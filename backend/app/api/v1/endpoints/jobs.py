from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_db_session
from app.core.permissions import require_admin, require_operator, require_viewer
from app.models.user import User
from app.schemas.job import JobCreate, JobUpdate, JobRead
from app.services.job_service import (
    create_job,
    update_job,
    delete_job,
    list_jobs,
    get_job,
    job_to_read,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobRead)
def create_job_endpoint(
    job_in: JobCreate,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    job = create_job(job_in, session)
    return job_to_read(job, session)


@router.put("/{job_id}", response_model=JobRead)
def update_job_endpoint(
    job_id: int,
    job_in: JobUpdate,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    job = update_job(job_id, job_in, session)
    return job_to_read(job, session)


@router.delete("/{job_id}")
def delete_job_endpoint(
    job_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    delete_job(job_id, session)
    return {"detail": "Job deleted successfully."}


@router.get("", response_model=list[JobRead])
def list_all_jobs(
    template_id: int | None = None,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    jobs = list_jobs(session, template_id=template_id)
    return [job_to_read(job, session) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
def get_job_details(
    job_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    job = get_job(job_id, session)
    return job_to_read(job, session)