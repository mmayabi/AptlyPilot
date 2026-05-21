from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.api.deps import get_db_session, get_current_active_user
from app.models.user import User
from app.models.job import Job, JobStatus
from app.services.job_service import create_job, get_job

router = APIRouter(prefix="/jobs/manual", tags=["manual-jobs"])

# ------------------------------
# Rerun یک Job موجود
# ------------------------------
@router.post("/{job_id}/rerun")
def rerun_job(
    job_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    job = get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")

    # اجازه rerun فقط برای FAILED یا SUCCESS
    if job.status not in [JobStatus.FAILED, JobStatus.SUCCESS]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Job {job_id} cannot be rerun. Current status: {job.status}")

    # Set job status to PENDING برای اینکه Worker آن را pick کند
    job.status = JobStatus.PENDING
    session.add(job)
    session.commit()
    session.refresh(job)

    return {
        "message": f"Job {job_id} set to PENDING for rerun",
        "job_id": job.id,
        "current_status": job.status
    }

# ------------------------------
# ایجاد Job جدید برای یک repo
# ------------------------------
@router.post("/create")
def create_manual_job(
    repo_id: int,
    steps: list[dict],
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    if not steps or len(steps) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No steps provided for manual job creation")

    job = create_job(session, repo_id=repo_id, steps=steps, triggered_by_user_id=current_user.id)

    return {
        "message": f"Manual Job created for repo {repo_id}",
        "job_id": job.id,
        "step_count": len(steps)
    }