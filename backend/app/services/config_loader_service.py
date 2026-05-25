from pathlib import Path

import yaml
from pydantic import ValidationError

from app.config import get_settings
from app.schemas.repo import ConfigValidationResponse, ReposConfigFile

settings = get_settings()

def get_repos_config_path() -> Path:
    return Path(getattr(settings, "REPOS_CONFIG_PATH"))


def load_repos_config_raw() -> dict:
    config_path = get_repos_config_path()
    with config_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_and_validate_repos_config() -> ReposConfigFile:
    raw_config = load_repos_config_raw()
    return ReposConfigFile.model_validate(raw_config)


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