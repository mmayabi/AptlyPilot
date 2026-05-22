# file: app/api/v1/endpoints/templates.py

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_db_session
from app.core.permissions import require_admin, require_operator, require_viewer
from app.models.user import User
from app.schemas.template import (
    JobTemplateCreate,
    JobTemplateUpdate,
    JobTemplateRead,
)
from app.services.template_service import (
    create_template,
    update_template,
    delete_template,
    list_templates,
    get_template,
    template_to_read,
)

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post("", response_model=JobTemplateRead)
def create_template_endpoint(
    template_in: JobTemplateCreate,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    template = create_template(template_in, session)
    return template_to_read(template, session)


@router.put("/{template_id}", response_model=JobTemplateRead)
def update_template_endpoint(
    template_id: int,
    template_in: JobTemplateUpdate,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    template = update_template(template_id, template_in, session)
    return template_to_read(template, session)


@router.delete("/{template_id}")
def delete_template_endpoint(
    template_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    delete_template(template_id, session)
    return {"detail": "Template deleted successfully."}


@router.get("", response_model=list[JobTemplateRead])
def list_templates_endpoint(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    templates = list_templates(session)
    return [template_to_read(template, session) for template in templates]


@router.get("/{template_id}", response_model=JobTemplateRead)
def get_template_endpoint(
    template_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    template = get_template(template_id, session)
    return template_to_read(template, session)