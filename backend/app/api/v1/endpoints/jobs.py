from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from app.api.deps import get_db_session, get_current_active_user
from app.models.user import User
from app.services.job_service import create_job, list_jobs, get_job, get_job_steps

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("", summary="List jobs")
def read_jobs(session: Session = Depends(get_db_session), current_user: User = Depends(get_current_active_user)):
    return list_jobs(session)

@router.get("/{job_id}", summary="Get job details")
def read_job(job_id: int, session: Session = Depends(get_db_session), current_user: User = Depends(get_current_active_user)):
    job = get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job

@router.get("/{job_id}/steps", summary="Get job steps")
def read_job_steps(job_id: int, session: Session = Depends(get_db_session), current_user: User = Depends(get_current_active_user)):
    return get_job_steps(session, job_id)

@router.post("/create", summary="Create a new job")
def create_new_job(repo_id: int, steps: list[dict], session: Session = Depends(get_db_session), current_user: User = Depends(get_current_active_user)):
    return create_job(session, repo_id, steps, triggered_by_user_id=current_user.id)