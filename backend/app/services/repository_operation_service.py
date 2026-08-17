from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.clients.aptly_client import AptlyClient
from app.models.aptly_state import AptlyPublishState, AptlySnapshotState
from app.models.repo import Repo
from app.services.aptly_inventory_service import sync_aptly_inventory


SCRIPT_MIRROR_UPDATE = "aptly.mirror.update"
SCRIPT_SNAPSHOT_CREATE = "aptly.snapshot.create"
SCRIPT_PUBLISH_SWITCH = "aptly.publish.switch"
SCRIPT_RETENTION_CLEANUP = "aptly.retention.cleanup"
SCRIPT_INVENTORY_SYNC = "aptly.inventory.sync"


SUPPORTED_REPOSITORY_OPERATION_SCRIPTS = {
    SCRIPT_MIRROR_UPDATE,
    SCRIPT_SNAPSHOT_CREATE,
    SCRIPT_PUBLISH_SWITCH,
    SCRIPT_RETENTION_CLEANUP,
    SCRIPT_INVENTORY_SYNC,
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def get_repo_or_404(session: Session, repo_id: int) -> Repo:
    repo = session.get(Repo, repo_id)

    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {repo_id}",
        )

    return repo


def get_effective_mirror_name(repo: Repo) -> str:
    return repo.mirror_name or repo.name


def build_snapshot_name(
    repo: Repo,
) -> str:
    timestamp = utc_now().strftime(repo.snapshot_timestamp_format)

    return repo.snapshot_naming.format(
        name=repo.name,
        mirror=get_effective_mirror_name(repo),
        provider=repo.provider,
        release=repo.release,
        timestamp=timestamp,
    )


def get_latest_snapshot_name_for_repo(
    session: Session,
    repo: Repo,
) -> str | None:
    mirror_name = get_effective_mirror_name(repo)

    snapshots = list(
        session.exec(
            select(AptlySnapshotState)
            .where(AptlySnapshotState.source_mirror_name == mirror_name)
            .order_by(AptlySnapshotState.created_at_aptly.desc())
        ).all()
    )

    if not snapshots:
        return None

    return snapshots[0].name


def get_publish_component(repo: Repo) -> str:
    if repo.publish_components:
        return repo.publish_components[0]

    if repo.mirror_components:
        return repo.mirror_components[0]

    return "main"


def get_publish_signing(repo: Repo) -> dict[str, Any] | None:
    if repo.publish_skip_signing:
        return None

    if repo.publish_gpg_key:
        return {
            "GpgKey": repo.publish_gpg_key,
        }

    return None


def run_mirror_update_operation(
    *,
    session: Session,
    repo: Repo,
    params: dict[str, Any],
    aptly_client: AptlyClient,
) -> dict[str, Any]:
    if not repo.mirror_enabled:
        return {
            "operation": SCRIPT_MIRROR_UPDATE,
            "skipped": True,
            "reason": "Mirror is disabled for this repository",
        }

    mirror_name = get_effective_mirror_name(repo)

    result = aptly_client.update_mirror(
        mirror_name=mirror_name,
        run_async=bool(params.get("run_async", True)),
        wait=bool(params.get("wait", True)),
        force_update=bool(params.get("force_update", False)),
        ignore_signatures=repo.mirror_ignore_signatures,
        skip_existing_packages=params.get("skip_existing_packages"),
        max_tries=repo.mirror_max_tries,
        poll_interval=int(params.get("poll_interval", 5)),
        max_wait_seconds=int(params.get("max_wait_seconds", 3600)),
    )

    sync_result = sync_aptly_inventory(
        session=session,
        aptly_client=aptly_client,
    )

    return {
        "operation": SCRIPT_MIRROR_UPDATE,
        "repo_id": repo.id,
        "repo_name": repo.name,
        "mirror_name": mirror_name,
        "result": result,
        "inventory_sync": sync_result,
    }


def run_snapshot_create_operation(
    *,
    session: Session,
    repo: Repo,
    params: dict[str, Any],
    aptly_client: AptlyClient,
) -> dict[str, Any]:
    if not repo.snapshot_enabled:
        return {
            "operation": SCRIPT_SNAPSHOT_CREATE,
            "skipped": True,
            "reason": "Snapshot is disabled for this repository",
        }

    mirror_name = get_effective_mirror_name(repo)
    snapshot_name = build_snapshot_name(repo)

    result = aptly_client.create_snapshot_from_mirror(
        mirror_name=mirror_name,
        snapshot_name=snapshot_name,
        description=(
            f"Snapshot for {repo.name} "
            f"from mirror {mirror_name}"
        ),
        fail_if_exists=bool(params.get("fail_if_exists", False)),
        run_async=bool(params.get("run_async", False)),
        wait=bool(params.get("wait", True)),
        poll_interval=int(params.get("poll_interval", 5)),
        max_wait_seconds=int(params.get("max_wait_seconds", 3600)),
    )

    sync_result = sync_aptly_inventory(
        session=session,
        aptly_client=aptly_client,
    )

    return {
        "operation": SCRIPT_SNAPSHOT_CREATE,
        "repo_id": repo.id,
        "repo_name": repo.name,
        "mirror_name": mirror_name,
        "snapshot_name": snapshot_name,
        "result": result,
        "inventory_sync": sync_result,
    }


def run_publish_switch_operation(
    *,
    session: Session,
    repo: Repo,
    params: dict[str, Any],
    aptly_client: AptlyClient,
) -> dict[str, Any]:
    if not repo.publish_enabled:
        return {
            "operation": SCRIPT_PUBLISH_SWITCH,
            "skipped": True,
            "reason": "Publish is disabled for this repository",
        }

    snapshot_name = get_latest_snapshot_name_for_repo(
        session=session,
        repo=repo,
    )

    if not snapshot_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No snapshot is available to publish",
        )

    distribution = repo.publish_distribution or repo.mirror_distribution
    prefix = repo.publish_prefix or "."
    storage = repo.publish_endpoint

    result = aptly_client.publish_or_switch_snapshot(
        snapshot_name=str(snapshot_name),
        prefix=prefix,
        storage=storage,
        distribution=distribution,
        component=get_publish_component(repo),
        architectures=repo.publish_architectures or repo.mirror_architectures,
        label=repo.publish_label,
        origin=repo.publish_origin,
        force_overwrite=bool(params.get("force_overwrite", False)),
        acquire_by_hash=repo.publish_acquire_by_hash,
        signing=get_publish_signing(repo),
    )

    sync_result = sync_aptly_inventory(
        session=session,
        aptly_client=aptly_client,
    )

    return {
        "operation": SCRIPT_PUBLISH_SWITCH,
        "repo_id": repo.id,
        "repo_name": repo.name,
        "snapshot_name": snapshot_name,
        "prefix": prefix,
        "storage": storage,
        "distribution": distribution,
        "result": result,
        "inventory_sync": sync_result,
    }


def run_inventory_sync_operation(
    *,
    session: Session,
    repo: Repo,
    aptly_client: AptlyClient,
) -> dict[str, Any]:
    return {
        "operation": SCRIPT_INVENTORY_SYNC,
        "repo_id": repo.id,
        "repo_name": repo.name,
        "result": sync_aptly_inventory(
            session=session,
            aptly_client=aptly_client,
        ),
    }


def get_published_snapshot_names(session: Session) -> set[str]:
    publishes = session.exec(select(AptlyPublishState)).all()
    names: set[str] = set()

    for publish in publishes:
        for source_name in publish.source_names or []:
            names.add(source_name)

    return names


def run_retention_cleanup_operation(
    *,
    session: Session,
    repo: Repo,
    params: dict[str, Any],
    aptly_client: AptlyClient,
) -> dict[str, Any]:
    mirror_name = get_effective_mirror_name(repo)
    keep_last = repo.retention_keep_last

    snapshots = list(
        session.exec(
            select(AptlySnapshotState)
            .where(AptlySnapshotState.source_mirror_name == mirror_name)
            .order_by(AptlySnapshotState.created_at_aptly.desc())
        ).all()
    )

    published_snapshot_names = get_published_snapshot_names(session)
    candidates = snapshots[keep_last:]
    deleted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for snapshot in candidates:
        if snapshot.name in published_snapshot_names:
            skipped.append(
                {
                    "snapshot_name": snapshot.name,
                    "reason": "Snapshot is currently published",
                }
            )
            continue

        try:
            deleted.append(
                aptly_client.delete_snapshot(
                    snapshot_name=snapshot.name,
                    force=bool(params.get("force", False)),
                )
            )
        except Exception as exc:
            errors.append(
                {
                    "snapshot_name": snapshot.name,
                    "error": str(exc),
                }
            )

    sync_result = sync_aptly_inventory(
        session=session,
        aptly_client=aptly_client,
    )

    return {
        "operation": SCRIPT_RETENTION_CLEANUP,
        "repo_id": repo.id,
        "repo_name": repo.name,
        "mirror_name": mirror_name,
        "keep_last": keep_last,
        "total_snapshots": len(snapshots),
        "deleted": deleted,
        "skipped": skipped,
        "errors": errors,
        "inventory_sync": sync_result,
    }


def run_repository_operation_step(
    *,
    script_name: str,
    session: Session,
    repo_id: int,
    params: dict[str, Any] | None,
    aptly_client: AptlyClient,
) -> dict[str, Any]:
    repo = get_repo_or_404(session, repo_id)
    params = params or {}

    started_at = utc_now()

    if script_name == SCRIPT_MIRROR_UPDATE:
        result = run_mirror_update_operation(
            session=session,
            repo=repo,
            params=params,
            aptly_client=aptly_client,
        )
    elif script_name == SCRIPT_SNAPSHOT_CREATE:
        result = run_snapshot_create_operation(
            session=session,
            repo=repo,
            params=params,
            aptly_client=aptly_client,
        )
    elif script_name == SCRIPT_PUBLISH_SWITCH:
        result = run_publish_switch_operation(
            session=session,
            repo=repo,
            params=params,
            aptly_client=aptly_client,
        )
    elif script_name == SCRIPT_RETENTION_CLEANUP:
        result = run_retention_cleanup_operation(
            session=session,
            repo=repo,
            params=params,
            aptly_client=aptly_client,
        )
    elif script_name == SCRIPT_INVENTORY_SYNC:
        result = run_inventory_sync_operation(
            session=session,
            repo=repo,
            aptly_client=aptly_client,
        )
    else:
        raise ValueError(f"Unsupported repository operation script: {script_name}")

    return {
        "status": "success",
        "script_name": script_name,
        "started_at": started_at.isoformat(),
        "finished_at": utc_now().isoformat(),
        **result,
    }
