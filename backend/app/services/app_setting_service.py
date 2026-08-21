from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.config import get_settings
from app.clients.aptly_client import AptlyClient
from app.db.session import engine
from app.models.app_setting import AppSetting


def get_app_setting_value(key: str, default: str | None = None) -> str | None:
    try:
        with Session(engine) as session:
            setting = session.get(AppSetting, key)
            if setting is not None:
                return setting.value
    except SQLAlchemyError:
        pass

    return str(getattr(get_settings(), key, default) or "")


def list_app_settings(keys: list[str] | None = None) -> dict[str, AppSetting]:
    with Session(engine) as session:
        query = select(AppSetting)
        if keys:
            query = query.where(AppSetting.key.in_(keys))

        return {
            setting.key: setting
            for setting in session.exec(query).all()
        }


def upsert_app_setting(
    session: Session,
    key: str,
    value: str | None,
    is_secret: bool = False,
) -> AppSetting:
    setting = session.get(AppSetting, key)
    now = datetime.utcnow()

    if setting is None:
        setting = AppSetting(
            key=key,
            value=value,
            is_secret=is_secret,
            created_at=now,
            updated_at=now,
        )
    else:
        setting.value = value
        setting.is_secret = is_secret
        setting.updated_at = now

    session.add(setting)
    return setting


def save_config_source_settings(
    *,
    source: str,
    gitlab_base_url: str,
    gitlab_project_id: str,
    gitlab_ref: str,
    gitlab_file_path: str,
    gitlab_token: str | None,
    clear_gitlab_token: bool,
    gitlab_timeout_seconds: int,
    session: Session,
) -> None:
    upsert_app_setting(session, "REPOS_CONFIG_SOURCE", source, is_secret=False)
    upsert_app_setting(session, "GITLAB_CONFIG_BASE_URL", gitlab_base_url, is_secret=False)
    upsert_app_setting(session, "GITLAB_CONFIG_PROJECT_ID", gitlab_project_id, is_secret=False)
    upsert_app_setting(session, "GITLAB_CONFIG_REF", gitlab_ref, is_secret=False)
    upsert_app_setting(session, "GITLAB_CONFIG_FILE_PATH", gitlab_file_path, is_secret=False)
    upsert_app_setting(
        session,
        "GITLAB_CONFIG_TIMEOUT_SECONDS",
        str(gitlab_timeout_seconds),
        is_secret=False,
    )

    if clear_gitlab_token:
        upsert_app_setting(session, "GITLAB_CONFIG_TOKEN", "", is_secret=True)
    elif gitlab_token:
        upsert_app_setting(session, "GITLAB_CONFIG_TOKEN", gitlab_token, is_secret=True)

    session.commit()


def get_aptly_connection_values() -> dict[str, str]:
    settings = get_settings()

    return {
        "url": get_app_setting_value("APTLY_API_URL", settings.APTLY_API_URL) or "",
        "username": get_app_setting_value(
            "APTLY_API_USERNAME",
            settings.APTLY_API_USERNAME or "",
        )
        or "",
        "password": get_app_setting_value(
            "APTLY_API_PASSWORD",
            settings.APTLY_API_PASSWORD or "",
        )
        or "",
        "token": get_app_setting_value(
            "APTLY_API_TOKEN",
            settings.APTLY_API_TOKEN or "",
        )
        or "",
    }


def make_aptly_client_from_settings() -> AptlyClient:
    values = get_aptly_connection_values()

    return AptlyClient(
        base_url=values["url"],
        username=values["username"] or None,
        password=values["password"] or None,
        token=values["token"] or None,
    )


def save_aptly_connection_settings(
    *,
    api_url: str,
    username: str,
    password: str | None,
    token: str | None,
    clear_password: bool,
    clear_token: bool,
    session: Session,
) -> None:
    upsert_app_setting(session, "APTLY_API_URL", api_url, is_secret=False)
    upsert_app_setting(session, "APTLY_API_USERNAME", username, is_secret=False)

    if clear_password:
        upsert_app_setting(session, "APTLY_API_PASSWORD", "", is_secret=True)
    elif password:
        upsert_app_setting(session, "APTLY_API_PASSWORD", password, is_secret=True)

    if clear_token:
        upsert_app_setting(session, "APTLY_API_TOKEN", "", is_secret=True)
    elif token:
        upsert_app_setting(session, "APTLY_API_TOKEN", token, is_secret=True)

    session.commit()
