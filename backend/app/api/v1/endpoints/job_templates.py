from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_db_session, get_current_active_user
from app.core.permissions import require_admin, require_operator, require_viewer
from app.models.user import User
from app.schemas.repo import RepoRead
from app.models.job_template import JobTemplate
from app.repositories.repo_repo import get_repo_by_name
from app.services.job_template_service import list_templates, get_template, create_template, update_template, delete_template
from app.services.job_service import create_job

router = APIRouter(prefix="/job-templates", tags=["job-templates"])

@router.get("", response_model=list[JobTemplate])
def read_templates(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    return list_templates(session)

@router.get("/{template_id}", response_model=JobTemplate)
def read_template(
    template_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    template = get_template(session, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template

@router.post("", response_model=JobTemplate)
def create_job_template(
    name: str,
    steps: list[dict],
    description: str | None = None,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    return create_template(session, name, steps, description, created_by=current_user.id)

@router.patch("/{template_id}", response_model=JobTemplate)
def update_job_template(
    template_id: int,
    name: str | None = None,
    steps: list[dict] | None = None,
    description: str | None = None,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    data = {k: v for k, v in {"name": name, "steps": steps, "description": description}.items() if v is not None}
    template = update_template(session, template_id, **data)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template

@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_template_endpoint(
    template_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    success = delete_template(session, template_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return None

@router.post("/create-job-from-template")
def create_job_from_template(
    template_id: int,
    repo_name: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    template = get_template(session, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job template not found")

    repo = get_repo_by_name(session, repo_name)
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Repository not found: {repo_name}")

    if not template.steps or len(template.steps) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Job template '{template.name}' has no steps defined")

    job = create_job(session, repo_id=repo.id, steps=template.steps, triggered_by_user_id=current_user.id)

    return {
        "message": f"Job created for repo '{repo.name}' using template '{template.name}'",
        "job_id": job.id,
        "step_count": len(job.steps) if hasattr(job, "steps") else len(template.steps)
    }