import difflib
import json
from copy import deepcopy
from typing import Any

import yaml
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.api.deps import get_db_session
from app.models.user import User
from app.schemas.repo import ReposConfigFile
from app.services.config_loader_service import (
    get_repos_config_location,
    get_repos_config_source,
    is_local_repos_config_source,
    load_repos_config_text,
    save_repos_config_text,
    validate_repos_config_text,
)
from app.services.repo_service import merge_repo_config, sync_repos_from_config
from app.ui.deps import get_web_admin

router = APIRouter(tags=["UI-Repositories"])

templates = Jinja2Templates(directory="app/templates")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _build_repository_entry_from_form(
    *,
    mirror_archive_url: str,
    mirror_distribution: str,
    mirror_components: str,
    mirror_architectures: str,
    mirror_name: str,
    mirror_ignore_signatures: bool,
    mirror_max_tries: int,
    snapshot_enabled: bool,
    snapshot_naming: str,
    snapshot_timestamp_format: str,
    publish_enabled: bool,
    publish_endpoint: str,
    publish_prefix: str,
    publish_distribution: str,
    publish_components: str,
    publish_architectures: str,
    publish_label: str,
    publish_origin: str,
    publish_codename: str,
    publish_suite: str,
    publish_skip_signing: bool,
    publish_gpg_key: str,
    publish_acquire_by_hash: bool,
    publish_skip_bz2: bool,
    publish_skip_contents: bool,
    test_enabled: bool,
    retention_keep_last: int,
    schedule_enabled: bool,
    schedule_type: str,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "mirror": {
            "archive_url": mirror_archive_url.strip(),
            "distribution": mirror_distribution.strip(),
            "components": _split_csv(mirror_components),
            "architectures": _split_csv(mirror_architectures),
            "ignore_signatures": mirror_ignore_signatures,
            "max_tries": mirror_max_tries,
        },
        "snapshot": {
            "enabled": snapshot_enabled,
            "naming": snapshot_naming.strip() or "{name}-{timestamp}",
            "timestamp_format": snapshot_timestamp_format.strip() or "%Y%m%d-%H%M",
        },
        "publish": {
            "enabled": publish_enabled,
            "endpoint": publish_endpoint.strip() or "filesystem:repository",
            "prefix": publish_prefix.strip(),
            "distribution": publish_distribution.strip() or None,
            "components": _split_csv(publish_components),
            "architectures": _split_csv(publish_architectures),
            "skip_signing": publish_skip_signing,
            "acquire_by_hash": publish_acquire_by_hash,
            "skip_bz2": publish_skip_bz2,
            "skip_contents": publish_skip_contents,
        },
        "test": {
            "enabled": test_enabled,
        },
        "retention": {
            "keep_last": retention_keep_last,
        },
        "schedule": {
            "enabled": schedule_enabled,
            "type": schedule_type,
        },
    }

    entry["mirror_name"] = mirror_name.strip()

    entry["publish"]["label"] = publish_label.strip() or None
    entry["publish"]["origin"] = publish_origin.strip() or None
    entry["publish"]["codename"] = publish_codename.strip() or None
    entry["publish"]["suite"] = publish_suite.strip() or None
    entry["publish"]["gpg_key"] = publish_gpg_key.strip() or None

    return entry


def _load_builder_config() -> tuple[str, dict]:
    # Never replace an unreadable or malformed source with an empty config.
    content = load_repos_config_text()
    config = yaml.safe_load(content) or {}
    ReposConfigFile.model_validate(config)
    return content, config


def _repository_key(provider: str, release: str, name: str) -> str:
    return json.dumps([provider, release, name], ensure_ascii=False)


def _form_values(config: dict, key: str) -> dict:
    provider, release, name = json.loads(key)
    parsed = ReposConfigFile.model_validate(config)
    resolved = merge_repo_config(
        provider, release, name, parsed.defaults, parsed.repos[provider][release][name]
    ).raw_config
    values = {
        "provider": provider,
        "release": release,
        "repo_name": name,
        "mirror_name": resolved.get("mirror_name") or "",
    }
    for section in ("mirror", "snapshot", "publish", "test", "retention", "schedule"):
        for field, value in resolved[section].items():
            values[f"{section}_{field}"] = (
                ", ".join(value) if isinstance(value, list) else value if value is not None else ""
            )
    return values


def _build_config_with_repository(
    *,
    provider: str,
    release: str,
    repo_name: str,
    repo_entry: dict[str, Any],
    current_config: dict,
    repository_key: str = "",
) -> str:
    config = deepcopy(current_config)
    provider, release, repo_name = provider.strip(), release.strip(), repo_name.strip()
    if not all((provider, release, repo_name)):
        raise ValueError("Provider, release and repository name are required.")
    release_repos = config.setdefault("repos", {}).setdefault(provider, {}).setdefault(release, {})
    if repository_key:
        if repository_key != _repository_key(provider, release, repo_name):
            raise ValueError("Repository identity cannot be changed while editing.")
        original = release_repos[repo_name]
        values = _form_values(current_config, repository_key)
        parsed = ReposConfigFile.model_validate(current_config)
        resolved = merge_repo_config(
            provider, release, repo_name, parsed.defaults,
            parsed.repos[provider][release][repo_name],
        ).raw_config
        for section, fields in repo_entry.items():
            if section == "mirror_name":
                if fields != values["mirror_name"]:
                    original[section] = fields or None
                continue
            for field, value in fields.items():
                # Only write fields changed in the form; preserve unknown fields and inheritance.
                old = values.get(f"{section}_{field}")
                if isinstance(value, list):
                    old = _split_csv(old or "")
                if value != old and not (value is None and old == ""):
                    if not isinstance(original.get(section), dict):
                        original[section] = deepcopy(resolved[section])
                    original[section][field] = value
    else:
        if repo_name in release_repos:
            raise ValueError("This repository already exists. Select it in the builder to edit it.")
        repo_entry = deepcopy(repo_entry)
        for field in ("distribution", "components", "architectures"):
            if not repo_entry["publish"][field]:
                repo_entry["publish"][field] = deepcopy(repo_entry["mirror"][field])
        repo_entry["test"]["checks"] = ["metadata"]
        release_repos[repo_name] = repo_entry
    return yaml.safe_dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _builder_error(request: Request, message: str):
    return templates.TemplateResponse(
        request=request, name="components/settings_error_result.html",
        context={"message": message},
    )


@router.get(
    "/repositories/config-builder",
    response_class=HTMLResponse,
)
def repository_config_builder(
    request: Request,
    repository_key: str = "",
    current_user: User = Depends(get_web_admin),
):
    try:
        _, config = _load_builder_config()
        choices = [
            {
                "key": _repository_key(provider, release, name),
                "label": f"{provider} / {release} / {name}",
            }
            for provider, releases in config["repos"].items()
            for release, repos in releases.items()
            for name in repos
        ]
        values = _form_values(config, repository_key) if repository_key else {}
    except Exception as exc:
        return _builder_error(request, f"Cannot load config: {exc}")
    return templates.TemplateResponse(
        request=request,
        name="components/repository_config_builder.html",
        context={
            "current_user": current_user,
            "repository_choices": choices,
            "repository_key": repository_key,
            "values": values,
            "config_source": get_repos_config_source(),
            "config_location": get_repos_config_location(),
            "config_is_local": is_local_repos_config_source(),
        },
    )


@router.post(
    "/repositories/config-builder/preview",
    response_class=HTMLResponse,
)
def preview_repository_config(
    request: Request,
    repository_key: str = Form(default=""),
    provider: str = Form(...),
    release: str = Form(...),
    repo_name: str = Form(...),
    mirror_archive_url: str = Form(...),
    mirror_distribution: str = Form(...),
    mirror_components: str = Form(...),
    mirror_architectures: str = Form(...),
    mirror_name: str = Form(default=""),
    mirror_ignore_signatures: bool = Form(default=False),
    mirror_max_tries: int = Form(default=3),
    snapshot_enabled: bool = Form(default=True),
    snapshot_naming: str = Form(default="{name}-{timestamp}"),
    snapshot_timestamp_format: str = Form(default="%Y%m%d-%H%M"),
    publish_enabled: bool = Form(default=True),
    publish_endpoint: str = Form(default="filesystem:repository"),
    publish_prefix: str = Form(default=""),
    publish_distribution: str = Form(default=""),
    publish_components: str = Form(default=""),
    publish_architectures: str = Form(default=""),
    publish_label: str = Form(default=""),
    publish_origin: str = Form(default=""),
    publish_codename: str = Form(default=""),
    publish_suite: str = Form(default=""),
    publish_skip_signing: bool = Form(default=False),
    publish_gpg_key: str = Form(default=""),
    publish_acquire_by_hash: bool = Form(default=False),
    publish_skip_bz2: bool = Form(default=False),
    publish_skip_contents: bool = Form(default=False),
    test_enabled: bool = Form(default=True),
    retention_keep_last: int = Form(default=3),
    schedule_enabled: bool = Form(default=False),
    schedule_type: str = Form(default="monthly"),
    current_user: User = Depends(get_web_admin),
):
    repo_entry = _build_repository_entry_from_form(
        mirror_archive_url=mirror_archive_url,
        mirror_distribution=mirror_distribution,
        mirror_components=mirror_components,
        mirror_architectures=mirror_architectures,
        mirror_name=mirror_name,
        mirror_ignore_signatures=mirror_ignore_signatures,
        mirror_max_tries=mirror_max_tries,
        snapshot_enabled=snapshot_enabled,
        snapshot_naming=snapshot_naming,
        snapshot_timestamp_format=snapshot_timestamp_format,
        publish_enabled=publish_enabled,
        publish_endpoint=publish_endpoint,
        publish_prefix=publish_prefix,
        publish_distribution=publish_distribution,
        publish_components=publish_components,
        publish_architectures=publish_architectures,
        publish_label=publish_label,
        publish_origin=publish_origin,
        publish_codename=publish_codename,
        publish_suite=publish_suite,
        publish_skip_signing=publish_skip_signing,
        publish_gpg_key=publish_gpg_key,
        publish_acquire_by_hash=publish_acquire_by_hash,
        publish_skip_bz2=publish_skip_bz2,
        publish_skip_contents=publish_skip_contents,
        test_enabled=test_enabled,
        retention_keep_last=retention_keep_last,
        schedule_enabled=schedule_enabled,
        schedule_type=schedule_type,
    )
    try:
        base_content, current_config = _load_builder_config()
        yaml_content = _build_config_with_repository(
            provider=provider, release=release, repo_name=repo_name,
            repo_entry=repo_entry, current_config=current_config, repository_key=repository_key,
        )
    except Exception as exc:
        return _builder_error(request, f"Cannot build config: {exc}")
    changes = "".join(difflib.unified_diff(
        base_content.splitlines(keepends=True), yaml_content.splitlines(keepends=True),
        fromfile="Current YAML", tofile="Proposed YAML",
    ))
    validation = validate_repos_config_text(yaml_content)

    return templates.TemplateResponse(
        request=request,
        name="components/repository_config_preview.html",
        context={
            "current_user": current_user,
            "config_source": get_repos_config_source(),
            "config_location": get_repos_config_location(),
            "config_is_local": is_local_repos_config_source(),
            "yaml_content": yaml_content,
            "base_content": base_content,
            "changes": changes,
            "validation": validation,
        },
    )


@router.post(
    "/repositories/config-builder/save",
    response_class=HTMLResponse,
)
def save_repository_config(
    request: Request,
    yaml_content: str = Form(...),
    base_content: str = Form(...),
    sync_after_save: bool = Form(default=False),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_web_admin),
):
    try:
        if load_repos_config_text() != base_content:
            return _builder_error(request, "Config changed since preview. Generate a new preview.")
    except Exception as exc:
        return _builder_error(request, f"Cannot read config: {exc}")
    validation = save_repos_config_text(yaml_content)
    sync_result = None

    if validation.valid and sync_after_save:
        sync_result = sync_repos_from_config(session)

    return templates.TemplateResponse(
        request=request,
        name="components/repository_config_save_result.html",
        headers={"HX-Refresh": "true"} if validation.valid else {},
        context={
            "current_user": current_user,
            "validation": validation,
            "sync_result": sync_result,
            "config_location": get_repos_config_location(),
        },
    )


@router.post("/repositories/config-builder/download")
def download_repository_config(
    yaml_content: str = Form(...),
    current_user: User = Depends(get_web_admin),
):
    validation = validate_repos_config_text(yaml_content)
    if not validation.valid:
        return Response(
            content="\n".join(validation.errors),
            media_type="text/plain",
            status_code=400,
        )

    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": 'attachment; filename="repos.yaml"',
        },
    )
