from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.config import get_settings
from app.schemas.repo import DefaultsConfig, RepoConfig, ReposConfigFile, ConfigValidationResponse

settings = get_settings()


class ConfigLoaderError(Exception):
    pass


def load_yaml_file(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or settings.REPOS_CONFIG_PATH)

    if not config_path.exists():
        raise ConfigLoaderError(f"Config file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ConfigLoaderError(f"Invalid YAML syntax: {exc}") from exc

    if data is None:
        raise ConfigLoaderError("Config file is empty")
    if not isinstance(data, dict):
        raise ConfigLoaderError("Config root must be a mapping/object")

    return data


def load_and_validate_repos_config(path: str | Path | None = None) -> ReposConfigFile:
    data = load_yaml_file(path)

    try:
        config_file = ReposConfigFile.model_validate(data)
    except ValidationError as exc:
        error_messages = []
        for error in exc.errors():
            location = ".".join(str(item) for item in error.get("loc", []))
            message = error.get("msg", "Invalid value")
            error_messages.append(f"{location}: {message}")
        raise ConfigLoaderError("; ".join(error_messages)) from exc

    defaults: DefaultsConfig | None = config_file.defaults

    # merge defaults
    for repo_name, repo in config_file.repos.items():
        if defaults:
            if repo.snapshot is None:
                repo.snapshot = defaults.snapshot
            if repo.publish is None:
                repo.publish = defaults.publish
            if repo.test is None:
                repo.test = defaults.test
            if repo.retention is None:
                repo.retention = defaults.retention

    return config_file


def validate_repos_config(path: str | None = None) -> ConfigValidationResponse:
    try:
        config = load_and_validate_repos_config(path)
    except ConfigLoaderError as exc:
        return ConfigValidationResponse(valid=False, repo_count=0, repos=[], errors=[str(exc)])

    return ConfigValidationResponse(
        valid=True,
        repo_count=len(config.repos),
        repos=sorted(config.repos.keys()),
        errors=[],
    )