from datetime import datetime
from sqlmodel import Session, select
from fastapi import HTTPException, status
from app.models.script import Script
from app.models.template import JobTemplate, JobStepTemplate
from app.models.job import Job
from app.models.worker_queue import WorkerQueueItem, WorkerQueueStatus
from app.schemas.template import JobTemplateCreate, JobTemplateUpdate, JobTemplateRead, JobStepTemplateRead
from app.models.job import JobStep

# -----------------------------
# Validation / Helpers
# -----------------------------
def check_script_exists(script_id: int, session: Session) -> None:
    script = session.get(Script, script_id)
    if not script:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Script not found: {script_id}",
        )


def get_template_or_404(template_id: int, session: Session) -> JobTemplate:
    template = session.get(JobTemplate, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found: {template_id}",
        )
    return template


def check_template_name_unique(
    name: str,
    session: Session,
    exclude_template_id: int | None = None,
) -> None:
    query = select(JobTemplate).where(JobTemplate.name == name)

    if exclude_template_id is not None:
        query = query.where(JobTemplate.id != exclude_template_id)

    existing = session.exec(query).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template name already exists: {name}",
        )


def check_no_active_jobs_for_template(template_id: int, session: Session) -> None:
    active_item = session.exec(
        select(WorkerQueueItem)
        .join(Job, WorkerQueueItem.job_id == Job.id)
        .where(
            Job.template_id == template_id,
            WorkerQueueItem.status.in_([
                WorkerQueueStatus.QUEUED,
                WorkerQueueStatus.RUNNING,
            ]),
        )
    ).first()

    if active_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update template because a job from this template is queued or running",
        )


def check_no_jobs_linked_to_template(template_id: int, session: Session) -> None:
    linked_job = session.exec(
        select(Job).where(Job.template_id == template_id)
    ).first()

    if linked_job:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete template because one or more jobs are linked to it",
        )

# -----------------------------
# mapper
# -----------------------------
def template_to_read(template: JobTemplate, session: Session) -> JobTemplateRead:
    """
    تبدیل مدل دیتابیس JobTemplate به schema خروجی JobTemplateRead.
    این mapper باعث می‌شود response همه endpointهای template یکسان باشد.
    """
    steps = get_template_steps(template.id, session)

    return JobTemplateRead(
        id=template.id,
        name=template.name,
        description=template.description,
        steps=[
            JobStepTemplateRead(
                id=step.id,
                script_id=step.script_id,
                order=step.order,
                description=step.description,
            )
            for step in steps
        ],
    )
# -----------------------------
# CRUD Template
# -----------------------------
def list_templates(session: Session) -> list[JobTemplate]:
    return list(session.exec(select(JobTemplate).order_by(JobTemplate.id)).all())


def get_template(template_id: int, session: Session) -> JobTemplate:
    return get_template_or_404(template_id, session)


def get_template_steps(template_id: int, session: Session) -> list[JobStepTemplate]:
    return list(
        session.exec(
            select(JobStepTemplate)
            .where(JobStepTemplate.template_id == template_id)
            .order_by(JobStepTemplate.order, JobStepTemplate.id)
        ).all()
    )


def create_template(template_in: JobTemplateCreate, session: Session) -> JobTemplate:
    check_template_name_unique(template_in.name, session)

    for step in template_in.steps:
        check_script_exists(step.script_id, session)

    template = JobTemplate(
        name=template_in.name,
        description=template_in.description,
    )

    session.add(template)
    session.commit()
    session.refresh(template)

    for step in template_in.steps:
        session.add(
            JobStepTemplate(
                template_id=template.id,
                script_id=step.script_id,
                order=step.order,
                description=step.description,
            )
        )

    session.commit()
    session.refresh(template)

    return template


def update_template(
    template_id: int,
    template_in: JobTemplateUpdate,
    session: Session,
) -> JobTemplate:
    template = get_template_or_404(template_id, session)

    check_no_active_jobs_for_template(template_id, session)

    if template_in.name is not None and template_in.name != template.name:
        check_template_name_unique(
            template_in.name,
            session,
            exclude_template_id=template_id,
        )
        template.name = template_in.name

    if template_in.description is not None:
        template.description = template_in.description

    template.updated_at = datetime.utcnow()
    session.add(template)

    # اگر steps در payload نیامده، stepها را دست نزن
    if template_in.steps is not None:
        existing_steps = get_template_steps(template_id, session)
        existing_by_id = {step.id: step for step in existing_steps}

        payload_ids: set[int] = set()

        for step_in in template_in.steps:
            check_script_exists(step_in.script_id, session)

            if step_in.id is None:
                session.add(
                    JobStepTemplate(
                        template_id=template_id,
                        script_id=step_in.script_id,
                        order=step_in.order,
                        description=step_in.description,
                    )
                )
                continue

            step = existing_by_id.get(step_in.id)
            if not step:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Step id {step_in.id} does not belong to "
                        f"template id {template_id}"
                    ),
                )

            payload_ids.add(step_in.id)

            step.script_id = step_in.script_id
            step.order = step_in.order
            step.description = step_in.description
            session.add(step)

        for existing_step in existing_steps:
            if existing_step.id not in payload_ids:
                session.delete(existing_step)

        # اول تغییرات template stepها را flush کن تا id stepهای جدید مشخص شود
        session.flush()

        # حالا jobهای pending را با template جدید sync کن
        sync_jobs_with_template(template_id, session)

    session.commit()
    session.refresh(template)

    return template


def delete_template(template_id: int, session: Session) -> None:
    template = get_template_or_404(template_id, session)

    check_no_jobs_linked_to_template(template_id, session)

    steps = get_template_steps(template_id, session)
    for step in steps:
        session.delete(step)

    session.delete(template)
    session.commit()

def has_active_worker_queue_for_job(job_id: int, session: Session) -> bool:
    """
    بررسی می‌کند آیا این job در حال حاضر در صف یا در حال اجراست یا نه.
    چون Job دیگر status اجرایی ندارد، وضعیت اجرا از WorkerQueue خوانده می‌شود.
    """
    active_item = session.exec(
        select(WorkerQueueItem).where(
            WorkerQueueItem.job_id == job_id,
            WorkerQueueItem.status.in_([
                WorkerQueueStatus.QUEUED,
                WorkerQueueStatus.RUNNING,
            ]),
        )
    ).first()

    return active_item is not None


def sync_jobs_with_template(template_id: int, session: Session) -> None:
    """
    همگام‌سازی JobStepهای Jobهای ساخته‌شده از یک Template با آخرین نسخه JobStepTemplateها.

    نکته:
    - Job و JobStep دیگر runtime state ندارند.
    - history اجرا در WorkerQueue است.
    - اگر job در صف یا در حال اجرا باشد، sync نمی‌شود تا اجرای جاری خراب نشود.
    """
    template_steps = get_template_steps(template_id, session)

    jobs = session.exec(
        select(Job).where(Job.template_id == template_id)
    ).all()

    for job in jobs:
        if has_active_worker_queue_for_job(job.id, session):
            continue

        existing_job_steps = session.exec(
            select(JobStep).where(JobStep.job_id == job.id)
        ).all()

        existing_by_template_step_id = {
            step.step_template_id: step
            for step in existing_job_steps
        }

        template_step_ids = {step.id for step in template_steps}

        # حذف stepهایی که دیگر در template نیستند
        for job_step in existing_job_steps:
            if job_step.step_template_id not in template_step_ids:
                session.delete(job_step)

        # اضافه یا آپدیت stepها براساس template جدید
        for template_step in template_steps:
            existing_job_step = existing_by_template_step_id.get(template_step.id)

            if existing_job_step:
                existing_job_step.script_id = template_step.script_id
                existing_job_step.order = template_step.order
                # params را دست نمی‌زنیم چون ممکن است مقادیر واقعی job باشند
                session.add(existing_job_step)
            else:
                session.add(
                    JobStep(
                        job_id=job.id,
                        step_template_id=template_step.id,
                        script_id=template_step.script_id,
                        order=template_step.order,
                        params={},
                    )
                )

        job.updated_at = datetime.utcnow()
        session.add(job)