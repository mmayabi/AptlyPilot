from datetime import datetime, UTC
from copy import deepcopy

from sqlmodel import Session

from app.models.repo import Repo, RepoStatus
from app.repositories.repo_repo import create_repo, get_repo_by_name, list_repos, save_repo
from app.schemas.repo import (
    ConfigValidationResponse,
    RepoConfigRead,
    RepoRead,
    RepoSyncItemResult,
    RepoSyncResponse,
)
from app.services.config_loader_service import load_and_validate_repos_config, validate_repos_config
from app.schemas.repo import MirrorConfig, SnapshotConfig, PublishConfig, TestConfig, RetentionConfig


def repo_to_read(repo: Repo) -> RepoRead:
    raw = repo.raw_config or {}
    repo_data = deepcopy(raw)
    defaults = raw.get("defaults", {})

    def merge_section(section_name: str, cls):
        section = repo_data.get(section_name, {})
        default_section = defaults.get(section_name, {}) if defaults else {}
        combined = {**default_section, **section}
        return cls.model_validate(combined)

    mirror = merge_section("mirror", MirrorConfig)
    snapshot = merge_section("snapshot", SnapshotConfig)
    publish = merge_section("publish", PublishConfig)
    test = merge_section("test", TestConfig)
    retention = merge_section("retention", RetentionConfig)

    return RepoRead(
        id=repo.id,
        name=repo.name,
        mirror_name=repo.mirror_name,
        enabled=repo.enabled,
        mirror=mirror,
        snapshot=snapshot,
        publish=publish,
        test=test,
        retention=retention,
        status=repo.status,
        last_sync_status=repo.last_sync_status,
        last_sync_at=repo.last_sync_at,
        last_error=repo.last_error,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


def get_all_repos(session: Session) -> list[Repo]:
    return list_repos(session)


def get_repo_or_none(session: Session, repo_name: str) -> Repo | None:
    return get_repo_by_name(session, repo_name)


def get_repo_config(session: Session, repo_name: str) -> RepoConfigRead | None:
    repo = get_repo_by_name(session, repo_name)
    if repo is None:
        return None
    return RepoConfigRead(name=repo.name, raw_config=repo.raw_config)


def validate_config_file() -> ConfigValidationResponse:
    return validate_repos_config()


def sync_repos_from_config(session: Session) -> RepoSyncResponse:
    config_file = load_and_validate_repos_config()

    created = 0
    updated = 0
    results: list[RepoSyncItemResult] = []

    for repo_name, repo_config in config_file.repos.items():
        existing_repo = get_repo_by_name(session, repo_name)
        raw_config = repo_config.model_dump(mode="json")

        mirror_name = getattr(repo_config, "mirror_name", repo_name)
        mirror_url = getattr(repo_config.mirror, "archive_url", None) if repo_config.mirror else None

        if existing_repo is None:
            repo = Repo(
                name=repo_name,
                mirror_name=mirror_name,
                enabled=repo_config.enabled,
                url=mirror_url,
                distribution=getattr(repo_config.mirror, "distribution", None),
                components=getattr(repo_config.mirror, "components", []),
                architectures=getattr(repo_config.mirror, "architectures", []),
                raw_config=raw_config,
                status=RepoStatus.UNKNOWN if repo_config.enabled else RepoStatus.DISABLED,
            )
            create_repo(session, repo)
            created += 1
            results.append(RepoSyncItemResult(name=repo_name, action="created"))
            continue

        # Update existing repo
        existing_repo.mirror_name = mirror_name
        existing_repo.enabled = repo_config.enabled
        existing_repo.url = mirror_url
        existing_repo.distribution = getattr(repo_config.mirror, "distribution", existing_repo.distribution)
        existing_repo.components = getattr(repo_config.mirror, "components", existing_repo.components)
        existing_repo.architectures = getattr(repo_config.mirror, "architectures", existing_repo.architectures)
        existing_repo.raw_config = raw_config
        existing_repo.updated_at = datetime.now(UTC).replace(tzinfo=None)

        if not repo_config.enabled:
            existing_repo.status = RepoStatus.DISABLED
        elif existing_repo.status == RepoStatus.DISABLED:
            existing_repo.status = RepoStatus.UNKNOWN

        save_repo(session, existing_repo)
        updated += 1
        results.append(RepoSyncItemResult(name=repo_name, action="updated"))

    return RepoSyncResponse(
        created=created,
        updated=updated,
        total=len(config_file.repos),
        repos=results,
    )