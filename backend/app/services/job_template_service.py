from datetime import datetime
from sqlmodel import Session, select
from app.models.job_template import JobTemplate

def list_templates(session: Session):
    statement = select(JobTemplate).order_by(JobTemplate.created_at.desc())
    return session.exec(statement).all()

def get_template(session: Session, template_id: int):
    return session.get(JobTemplate, template_id)

def create_template(session: Session, name: str, steps: list[dict], description: str | None, created_by: int | None):
    template = JobTemplate(
        name=name,
        steps=steps,
        description=description,
        created_by=created_by,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    session.add(template)
    session.commit()
    session.refresh(template)
    return template

def update_template(session: Session, template_id: int, **kwargs):
    template = session.get(JobTemplate, template_id)
    if not template:
        return None
    for k, v in kwargs.items():
        setattr(template, k, v)
    template.updated_at = datetime.now()
    session.add(template)
    session.commit()
    session.refresh(template)
    return template

def delete_template(session: Session, template_id: int):
    template = session.get(JobTemplate, template_id)
    if not template:
        return False
    session.delete(template)
    session.commit()
    return True