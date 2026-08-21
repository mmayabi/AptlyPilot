from pathlib import Path
from urllib.parse import quote

import requests
import yaml
from pydantic import ValidationError

from app.config import get_settings
from app.schemas.repo import ConfigValidationResponse, ReposConfigFile
from app.services.app_setting_service import get_app_setting_value

settings = get_settings()

def get_repos_config_path() -> Path:
    return Path(get_app_setting_value("REPOS_CONFIG_PATH", settings.REPOS_CONFIG_PATH) or "")


def get_repos_config_source() -> str:
    return (get_app_setting_value("REPOS_CONFIG_SOURCE", settings.REPOS_CONFIG_SOURCE) or "local").lower()


def is_local_repos_config_source() -> bool:
    return get_repos_config_source() == "local"


def get_repos_config_location() -> str:
    if is_local_repos_config_source():
        return str(get_repos_config_path())

    if get_repos_config_source() == "gitlab":
        gitlab_base_url = get_app_setting_value(
            "GITLAB_CONFIG_BASE_URL",
            settings.GITLAB_CONFIG_BASE_URL,
        )
        gitlab_project_id = get_app_setting_value(
            "GITLAB_CONFIG_PROJECT_ID",
            settings.GITLAB_CONFIG_PROJECT_ID or "",
        )
        gitlab_ref = get_app_setting_value(
            "GITLAB_CONFIG_REF",
            settings.GITLAB_CONFIG_REF,
        )
        gitlab_file_path = get_app_setting_value(
            "GITLAB_CONFIG_FILE_PATH",
            settings.GITLAB_CONFIG_FILE_PATH or "",
        )
        return (
            f"{gitlab_base_url}/"
            f"{gitlab_project_id}:"
            f"{gitlab_file_path}@{gitlab_ref}"
        )

    return get_repos_config_source()


def get_gitlab_config_raw_url() -> str:
    gitlab_project_id = get_app_setting_value(
        "GITLAB_CONFIG_PROJECT_ID",
        settings.GITLAB_CONFIG_PROJECT_ID or "",
    )
    gitlab_file_path = get_app_setting_value(
        "GITLAB_CONFIG_FILE_PATH",
        settings.GITLAB_CONFIG_FILE_PATH or "",
    )
    gitlab_base_url = get_app_setting_value(
        "GITLAB_CONFIG_BASE_URL",
        settings.GITLAB_CONFIG_BASE_URL,
    )
    gitlab_ref = get_app_setting_value("GITLAB_CONFIG_REF", settings.GITLAB_CONFIG_REF)

    if not gitlab_project_id:
        raise ValueError("GITLAB_CONFIG_PROJECT_ID is required when REPOS_CONFIG_SOURCE=gitlab")

    if not gitlab_file_path:
        raise ValueError("GITLAB_CONFIG_FILE_PATH is required when REPOS_CONFIG_SOURCE=gitlab")

    base_url = (gitlab_base_url or "https://gitlab.com").rstrip("/")
    project_id = quote(gitlab_project_id, safe="")
    file_path = quote(gitlab_file_path, safe="")

    return (
        f"{base_url}/api/v4/projects/{project_id}/repository/files/"
        f"{file_path}/raw?ref={quote(gitlab_ref or 'main', safe='')}"
    )


def load_repos_config_text_from_gitlab() -> str:
    headers = {}
    token = get_app_setting_value("GITLAB_CONFIG_TOKEN", settings.GITLAB_CONFIG_TOKEN or "") or None
    if token:
        headers["PRIVATE-TOKEN"] = token

    response = requests.get(
        get_gitlab_config_raw_url(),
        headers=headers,
        timeout=int(
            get_app_setting_value(
                "GITLAB_CONFIG_TIMEOUT_SECONDS",
                str(settings.GITLAB_CONFIG_TIMEOUT_SECONDS),
            )
            or settings.GITLAB_CONFIG_TIMEOUT_SECONDS
        ),
    )
    response.raise_for_status()

    return response.text


def load_repos_config_raw() -> dict:
    return yaml.safe_load(load_repos_config_text()) or {}


def load_repos_config_text() -> str:
    source = get_repos_config_source()
    if source == "gitlab":
        return load_repos_config_text_from_gitlab()

    if source != "local":
        raise ValueError(f"Unsupported REPOS_CONFIG_SOURCE: {source}")

    config_path = get_repos_config_path()
    return config_path.read_text(encoding="utf-8")


def parse_repos_config_text(config_text: str) -> ReposConfigFile:
    raw_config = yaml.safe_load(config_text) or {}
    return ReposConfigFile.model_validate(raw_config)


def load_and_validate_repos_config() -> ReposConfigFile:
    raw_config = load_repos_config_raw()
    return ReposConfigFile.model_validate(raw_config)


def validation_response_from_config(config: ReposConfigFile) -> ConfigValidationResponse:
    repo_names: list[str] = []
    for provider, releases in config.repos.items():
        for release, repos in releases.items():
            for repo_name in repos:
                repo_names.append(f"{provider}/{release}/{repo_name}")

    return ConfigValidationResponse(
        valid=True,
        repo_count=len(repo_names),
        repos=repo_names,
        errors=[],
    )


def validate_repos_config_text(config_text: str) -> ConfigValidationResponse:
    try:
        config = parse_repos_config_text(config_text)
    except ValidationError as exc:
        return ConfigValidationResponse(
            valid=False,
            repo_count=0,
            repos=[],
            errors=[str(error) for error in exc.errors()],
        )
    except Exception as exc:
        return ConfigValidationResponse(
            valid=False,
            repo_count=0,
            repos=[],
            errors=[str(exc)],
        )

    return validation_response_from_config(config)


def save_repos_config_text(config_text: str) -> ConfigValidationResponse:
    if not is_local_repos_config_source():
        return ConfigValidationResponse(
            valid=False,
            repo_count=0,
            repos=[],
            errors=["Saving config from UI is only supported when REPOS_CONFIG_SOURCE=local"],
        )

    validation = validate_repos_config_text(config_text)
    if not validation.valid:
        return validation

    config_path = get_repos_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")

    return validation


def validate_repos_config() -> ConfigValidationResponse:
    try:
        config = load_and_validate_repos_config()
    except ValidationError as exc:
        return ConfigValidationResponse(
            valid=False,
            repo_count=0,
            repos=[],
            errors=[str(error) for error in exc.errors()],
        )
    except Exception as exc:
        return ConfigValidationResponse(
            valid=False,
            repo_count=0,
            repos=[],
            errors=[str(exc)],
        )

    return validation_response_from_config(config)
