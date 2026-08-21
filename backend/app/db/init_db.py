from sqlmodel import SQLModel
from app.config import get_settings
from app.db import base  # noqa: F401
from app.db.session import engine
from app.models.app_setting import AppSetting
from app.models.script import Script
from app.models.template import JobTemplate, JobStepTemplate
from app.scripts.aptly_default_scripts import DEFAULT_JOB_TEMPLATES, DEFAULT_SCRIPTS
from sqlmodel import Session, select


CONFIG_SETTING_KEYS = [
    ("REPOS_CONFIG_SOURCE", "local", False),
    ("REPOS_CONFIG_PATH", "/app/config/repos.yaml", False),
    ("GITLAB_CONFIG_BASE_URL", "https://gitlab.com", False),
    ("GITLAB_CONFIG_PROJECT_ID", "", False),
    ("GITLAB_CONFIG_REF", "main", False),
    ("GITLAB_CONFIG_FILE_PATH", "", False),
    ("GITLAB_CONFIG_TOKEN", "", True),
    ("GITLAB_CONFIG_TIMEOUT_SECONDS", "20", False),
    ("APTLY_API_URL", "http://127.0.0.1:8080", False),
    ("APTLY_API_USERNAME", "", False),
    ("APTLY_API_PASSWORD", "", True),
    ("APTLY_API_TOKEN", "", True),
]

def seed_scripts():
    """Insert default scripts if they do not exist"""
    with Session(engine) as session:
        for s in DEFAULT_SCRIPTS:
            stmt = select(Script).where(Script.name == s["name"])
            existing = session.exec(stmt).first()
            if not existing:
                script = Script(**s)
                session.add(script)
                continue

            existing.description = s.get("description")
            existing.params = s.get("params") or {}
            if "timeout_seconds" in s:
                existing.timeout_seconds = s["timeout_seconds"]
            if "max_retries" in s:
                existing.max_retries = s["max_retries"]
            if "retry_delay_seconds" in s:
                existing.retry_delay_seconds = s["retry_delay_seconds"]
            session.add(existing)
        session.commit()


def seed_job_templates():
    """Insert default job templates if they do not exist."""
    with Session(engine) as session:
        scripts_by_name = {
            script.name: script
            for script in session.exec(select(Script)).all()
        }

        for template_data in DEFAULT_JOB_TEMPLATES:
            existing_template = session.exec(
                select(JobTemplate).where(JobTemplate.name == template_data["name"])
            ).first()

            if existing_template:
                continue

            template = JobTemplate(
                name=template_data["name"],
                description=template_data.get("description"),
            )
            session.add(template)
            session.flush()

            for step_data in template_data["steps"]:
                script = scripts_by_name.get(step_data["script_name"])
                if script is None:
                    raise RuntimeError(
                        f"Default script not found for template seed: "
                        f"{step_data['script_name']}"
                    )

                session.add(
                    JobStepTemplate(
                        template_id=template.id,
                        script_id=script.id,
                        order=step_data["order"],
                        description=step_data.get("description"),
                    )
                )

        session.commit()


def seed_app_settings():
    settings = get_settings()

    with Session(engine) as session:
        for key, default_value, is_secret in CONFIG_SETTING_KEYS:
            existing = session.get(AppSetting, key)
            if existing:
                continue

            value = str(getattr(settings, key, default_value) or "")
            session.add(
                AppSetting(
                    key=key,
                    value=value,
                    is_secret=is_secret,
                )
            )

        session.commit()


def init_db() -> None:
    """Create all tables and seed default scripts"""
    SQLModel.metadata.create_all(engine)  # ایجاد تمام جداول
    seed_app_settings()
    seed_scripts()  # اضافه کردن scriptهای پیش‌فرض
    seed_job_templates()  # اضافه کردن templateهای پیش‌فرض
