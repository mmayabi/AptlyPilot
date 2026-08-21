from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.aptly_state import AptlyMirrorState, AptlyPublishState, AptlySnapshotState
from app.models.job import Job, JobStep
from app.models.repo import Repo
from app.models.script import Script
from app.models.worker_queue import WorkerQueueItem, WorkerQueueStatus


UPDATE_WARNING_DAYS = 7


# ----------------------------
# Helper functions
# ----------------------------

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def days_since(value: datetime | None) -> int | None:
    value = as_aware_utc(value)
    if value is None:
        return None

    return (utc_now() - value).days


def get_effective_mirror_name(repo: Repo) -> str:
    return repo.mirror_name or repo.name


def list_contains(values: list[Any] | None, item: str) -> bool:
    if not values:
        return False

    return item in values


def find_publishes_by_snapshot_name(
    publishes: list[AptlyPublishState],
    snapshot_name: str,
) -> list[AptlyPublishState]:
    """
    Find publish entries that reference the given snapshot name.

    This filtering is intentionally done in Python instead of using JSON/JSONB
    SQL operators, because the current model may use sqlalchemy.JSON instead
    of PostgreSQL JSONB.
    """

    return [
        publish
        for publish in publishes
        if list_contains(publish.source_names, snapshot_name)
    ]


def find_publishes_by_snapshot_names(
    publishes: list[AptlyPublishState],
    snapshot_names: list[str],
) -> list[AptlyPublishState]:
    snapshot_name_set = set(snapshot_names)

    return [
        publish
        for publish in publishes
        if snapshot_name_set.intersection(set(publish.source_names or []))
    ]


def get_latest_snapshot(
    snapshots: list[AptlySnapshotState],
) -> AptlySnapshotState | None:
    valid_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.created_at_aptly is not None
    ]

    if not valid_snapshots:
        return None

    return max(
        valid_snapshots,
        key=lambda snapshot: as_aware_utc(snapshot.created_at_aptly)
        or datetime.min.replace(tzinfo=timezone.utc),
    )


def get_latest_published_snapshot(
    snapshots: list[AptlySnapshotState],
    publishes: list[AptlyPublishState],
) -> AptlySnapshotState | None:
    published_snapshot_names: set[str] = set()

    for publish in publishes:
        for source_name in publish.source_names or []:
            published_snapshot_names.add(source_name)

    published_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.name in published_snapshot_names
        and snapshot.created_at_aptly is not None
    ]

    if not published_snapshots:
        return None

    return max(
        published_snapshots,
        key=lambda snapshot: as_aware_utc(snapshot.created_at_aptly)
        or datetime.min.replace(tzinfo=timezone.utc),
    )


def calculate_retention_status(
    repo: Repo,
    snapshots: list[AptlySnapshotState],
) -> str:
    if len(snapshots) > repo.retention_keep_last:
        return "exceeded"

    return "ok"


def calculate_pipeline_status(
    mirror: AptlyMirrorState | None,
    snapshots: list[AptlySnapshotState],
    latest_snapshot: AptlySnapshotState | None,
    latest_snapshot_publishes: list[AptlyPublishState],
    latest_mirror_has_snapshot: bool,
    latest_snapshot_is_published: bool,
    publish_matches_latest_mirror_update: bool,
) -> str:
    if mirror is None:
        return "mirror_missing"

    if not snapshots:
        return "no_snapshots"

    if latest_snapshot is None:
        return "no_snapshots"

    if not latest_mirror_has_snapshot:
        return "mirror_updated_not_snapshotted"

    if not latest_snapshot_is_published:
        return "snapshot_created_not_published"

    if latest_snapshot_publishes and not publish_matches_latest_mirror_update:
        return "published_snapshot_is_outdated"

    return "complete"


def determine_compliance_status(
    compliance_issues: list[dict[str, Any]],
) -> str:
    if compliance_issues:
        return "non_compliant"

    return "compliant"


def determine_health_status(
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    if errors:
        return "critical"

    if warnings:
        return "warning"

    return "healthy"


def aggregate_operational_status(items: list[dict[str, Any]]) -> str:
    statuses = [item["operational_status"] for item in items]

    if "running" in statuses:
        return "running"

    if "pending" in statuses:
        return "pending"

    if "failed" in statuses:
        return "failed"

    return "idle"


def get_repo_operation_states(
    session: Session,
    repo_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not repo_ids:
        return {}

    jobs = session.exec(select(Job).where(Job.repo_id.in_(repo_ids))).all()
    jobs_by_id = {job.id: job for job in jobs if job.id is not None}
    job_ids = list(jobs_by_id.keys())
    if not job_ids:
        return {}

    items = session.exec(
        select(WorkerQueueItem)
        .where(WorkerQueueItem.job_id.in_(job_ids))
        .order_by(WorkerQueueItem.created_at.desc(), WorkerQueueItem.id.desc())
    ).all()

    step_ids = [item.job_step_id for item in items]
    steps_by_id = {}
    scripts_by_id = {}
    if step_ids:
        steps = session.exec(select(JobStep).where(JobStep.id.in_(step_ids))).all()
        steps_by_id = {step.id: step for step in steps if step.id is not None}

        script_ids = [step.script_id for step in steps]
        if script_ids:
            scripts = session.exec(select(Script).where(Script.id.in_(script_ids))).all()
            scripts_by_id = {script.id: script for script in scripts if script.id is not None}

    states: dict[int, dict[str, Any]] = {}

    for wanted_status, operational_status in [
        (WorkerQueueStatus.RUNNING, "running"),
        (WorkerQueueStatus.QUEUED, "pending"),
    ]:
        for item in items:
            if item.status != wanted_status:
                continue

            job = jobs_by_id.get(item.job_id)
            if job is None or job.repo_id in states:
                continue

            step = steps_by_id.get(item.job_step_id)
            script = scripts_by_id.get(step.script_id) if step else None
            states[job.repo_id] = {
                "operational_status": operational_status,
                "current_operation_type": script.name if script else None,
                "current_job_id": item.job_id,
                "current_queue_item_id": item.id,
                "current_execution_id": item.execution_id,
            }

    latest_by_repo_id: dict[int, WorkerQueueItem] = {}
    for item in items:
        job = jobs_by_id.get(item.job_id)
        if job is None or job.repo_id in latest_by_repo_id:
            continue
        latest_by_repo_id[job.repo_id] = item

    for repo_id, item in latest_by_repo_id.items():
        if repo_id in states or item.status != WorkerQueueStatus.FAILED:
            continue

        step = steps_by_id.get(item.job_step_id)
        script = scripts_by_id.get(step.script_id) if step else None
        states[repo_id] = {
            "operational_status": "failed",
            "current_operation_type": script.name if script else None,
            "current_job_id": item.job_id,
            "current_queue_item_id": item.id,
            "current_execution_id": item.execution_id,
        }

    return states


def aggregate_health_status(items: list[dict[str, Any]]) -> str:
    statuses = [item["health_status"] for item in items]

    if "critical" in statuses:
        return "critical"

    if "warning" in statuses:
        return "warning"

    if "unknown" in statuses:
        return "unknown"

    return "healthy"


def aggregate_compliance_status(items: list[dict[str, Any]]) -> str:
    statuses = [item["compliance_status"] for item in items]

    if "non_compliant" in statuses:
        return "non_compliant"

    if "unknown" in statuses:
        return "unknown"

    return "compliant"


def count_items(items: list[dict[str, Any]], field: str, value: str) -> int:
    return sum(1 for item in items if item.get(field) == value)


def get_latest_datetime(values: list[datetime | None]) -> datetime | None:
    valid_values = [
        as_aware_utc(value)
        for value in values
        if value is not None
    ]

    if not valid_values:
        return None

    return max(valid_values)


def get_oldest_datetime(values: list[datetime | None]) -> datetime | None:
    valid_values = [
        as_aware_utc(value)
        for value in values
        if value is not None
    ]

    if not valid_values:
        return None

    return min(valid_values)


# ----------------------------
# Builders
# ----------------------------

def build_repo_dashboard_item(
    repo: Repo,
    mirrors_by_name: dict[str, AptlyMirrorState],
    snapshots_by_source_mirror: dict[str, list[AptlySnapshotState]],
    all_publishes: list[AptlyPublishState],
    operation_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective_mirror_name = get_effective_mirror_name(repo)

    mirror = mirrors_by_name.get(effective_mirror_name)
    snapshots = snapshots_by_source_mirror.get(effective_mirror_name, [])

    latest_snapshot = get_latest_snapshot(snapshots)

    snapshot_names = [snapshot.name for snapshot in snapshots]
    related_publishes = find_publishes_by_snapshot_names(
        publishes=all_publishes,
        snapshot_names=snapshot_names,
    )

    latest_snapshot_publishes: list[AptlyPublishState] = []
    if latest_snapshot:
        latest_snapshot_publishes = find_publishes_by_snapshot_name(
            publishes=all_publishes,
            snapshot_name=latest_snapshot.name,
        )

    latest_published_snapshot = get_latest_published_snapshot(
        snapshots=snapshots,
        publishes=related_publishes,
    )

    latest_mirror_update_at = mirror.last_download_date if mirror else None
    latest_snapshot_created_at = latest_snapshot.created_at_aptly if latest_snapshot else None
    latest_published_snapshot_created_at = (
        latest_published_snapshot.created_at_aptly
        if latest_published_snapshot
        else None
    )

    latest_mirror_update_at_utc = as_aware_utc(latest_mirror_update_at)
    latest_snapshot_created_at_utc = as_aware_utc(latest_snapshot_created_at)
    latest_published_snapshot_created_at_utc = as_aware_utc(
        latest_published_snapshot_created_at
    )

    latest_mirror_has_snapshot = False
    if latest_mirror_update_at_utc and latest_snapshot_created_at_utc:
        latest_mirror_has_snapshot = (
            latest_snapshot_created_at_utc >= latest_mirror_update_at_utc
        )

    latest_snapshot_is_published = bool(latest_snapshot_publishes)

    publish_matches_latest_mirror_update = False
    if (
        latest_mirror_update_at_utc
        and latest_published_snapshot_created_at_utc
    ):
        publish_matches_latest_mirror_update = (
            latest_published_snapshot_created_at_utc >= latest_mirror_update_at_utc
        )

    retention_status = calculate_retention_status(
        repo=repo,
        snapshots=snapshots,
    )

    compliance_issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if repo.mirror_enabled and mirror is None:
        error = {
            "code": "MIRROR_MISSING",
            "severity": "critical",
            "message": "Mirror is enabled in config but was not found in Aptly inventory",
        }
        errors.append(error)
        compliance_issues.append(error)

    if mirror:
        if repo.mirror_distribution != mirror.distribution:
            compliance_issues.append(
                {
                    "code": "MIRROR_DISTRIBUTION_MISMATCH",
                    "severity": "warning",
                    "message": "Mirror distribution in Aptly does not match repo config",
                    "expected": repo.mirror_distribution,
                    "actual": mirror.distribution,
                }
            )

        configured_components = sorted(repo.mirror_components or [])
        actual_components = sorted(mirror.components or [])
        if configured_components != actual_components:
            compliance_issues.append(
                {
                    "code": "MIRROR_COMPONENTS_MISMATCH",
                    "severity": "warning",
                    "message": "Mirror components in Aptly do not match repo config",
                    "expected": configured_components,
                    "actual": actual_components,
                }
            )

        configured_architectures = sorted(repo.mirror_architectures or [])
        actual_architectures = sorted(mirror.architectures or [])
        if configured_architectures != actual_architectures:
            compliance_issues.append(
                {
                    "code": "MIRROR_ARCHITECTURES_MISMATCH",
                    "severity": "warning",
                    "message": "Mirror architectures in Aptly do not match repo config",
                    "expected": configured_architectures,
                    "actual": actual_architectures,
                }
            )

    if repo.snapshot_enabled and not snapshots:
        error = {
            "code": "NO_SNAPSHOTS",
            "severity": "critical",
            "message": "Snapshot is enabled in config but no related snapshot was found",
        }
        errors.append(error)
        compliance_issues.append(error)

    if retention_status == "exceeded":
        warning = {
            "code": "RETENTION_EXCEEDED",
            "severity": "warning",
            "message": (
                f"Snapshot retention exceeded: expected max "
                f"{repo.retention_keep_last}, actual {len(snapshots)}"
            ),
            "expected": repo.retention_keep_last,
            "actual": len(snapshots),
        }
        warnings.append(warning)
        compliance_issues.append(warning)

    if repo.publish_enabled and not related_publishes:
        error = {
            "code": "PUBLISH_MISSING",
            "severity": "critical",
            "message": "Publish is enabled in config but no related publish entry was found",
        }
        errors.append(error)
        compliance_issues.append(error)

    if repo.publish_enabled and latest_snapshot and not latest_snapshot_is_published:
        warning = {
            "code": "LATEST_SNAPSHOT_NOT_PUBLISHED",
            "severity": "warning",
            "message": "Latest snapshot is not published",
            "snapshot_name": latest_snapshot.name,
        }
        warnings.append(warning)
        compliance_issues.append(warning)

    if mirror and latest_snapshot and not latest_mirror_has_snapshot:
        warning = {
            "code": "LATEST_MIRROR_WITHOUT_SNAPSHOT",
            "severity": "warning",
            "message": "Latest mirror update does not have a corresponding snapshot",
            "latest_mirror_update_at": latest_mirror_update_at,
            "latest_snapshot_created_at": latest_snapshot_created_at,
        }
        warnings.append(warning)
        compliance_issues.append(warning)

    if related_publishes and latest_published_snapshot and not publish_matches_latest_mirror_update:
        warning = {
            "code": "PUBLISHED_SNAPSHOT_OUTDATED",
            "severity": "warning",
            "message": "Published snapshot is older than the latest mirror update",
            "latest_mirror_update_at": latest_mirror_update_at,
            "published_snapshot_created_at": latest_published_snapshot_created_at,
        }
        warnings.append(warning)
        compliance_issues.append(warning)

    mirror_update_age_days = days_since(latest_mirror_update_at)
    if mirror_update_age_days is not None and mirror_update_age_days > UPDATE_WARNING_DAYS:
        warnings.append(
            {
                "code": "MIRROR_UPDATE_OLD",
                "severity": "warning",
                "message": f"Last mirror download is older than {UPDATE_WARNING_DAYS} days",
                "days_since_last_download": mirror_update_age_days,
            }
        )

    pipeline_status = calculate_pipeline_status(
        mirror=mirror,
        snapshots=snapshots,
        latest_snapshot=latest_snapshot,
        latest_snapshot_publishes=latest_snapshot_publishes,
        latest_mirror_has_snapshot=latest_mirror_has_snapshot,
        latest_snapshot_is_published=latest_snapshot_is_published,
        publish_matches_latest_mirror_update=publish_matches_latest_mirror_update,
    )

    compliance_status = determine_compliance_status(compliance_issues)
    health_status = determine_health_status(errors=errors, warnings=warnings)

    publish = related_publishes[0] if related_publishes else None
    operation_state = operation_state or {}

    return {
        "repo_id": repo.id,
        "provider": repo.provider,
        "release": repo.release,
        "name": repo.name,
        "effective_mirror_name": effective_mirror_name,

        "mirror_enabled": repo.mirror_enabled,
        "snapshot_enabled": repo.snapshot_enabled,
        "publish_enabled": repo.publish_enabled,

        "mirror_exists": mirror is not None,
        "mirror_distribution": mirror.distribution if mirror else repo.mirror_distribution,
        "mirror_archive_url": mirror.archive_root if mirror else repo.mirror_archive_url,
        "mirror_components": mirror.components if mirror else repo.mirror_components,
        "mirror_architectures": mirror.architectures if mirror else repo.mirror_architectures,

        "latest_mirror_update_at": latest_mirror_update_at,
        "last_download_date": latest_mirror_update_at,
        "days_since_last_download": mirror_update_age_days,

        "snapshots_count": len(snapshots),
        "retention_keep_last": repo.retention_keep_last,
        "retention_status": retention_status,

        "latest_snapshot_name": latest_snapshot.name if latest_snapshot else None,
        "latest_snapshot_created_at": latest_snapshot_created_at,
        "latest_mirror_has_snapshot": latest_mirror_has_snapshot,

        "publish_exists": bool(related_publishes),
        "publish_id": publish.id if publish else None,
        "publish_prefix": publish.prefix if publish else None,
        "publish_distribution": publish.distribution if publish else None,
        "publish_path": publish.path if publish else None,

        "latest_snapshot_is_published": latest_snapshot_is_published,

        "published_snapshot_name": latest_published_snapshot.name if latest_published_snapshot else None,
        "published_snapshot_created_at": latest_published_snapshot_created_at,
        "publish_matches_latest_mirror_update": publish_matches_latest_mirror_update,

        "pipeline_status": pipeline_status,

        "operational_status": operation_state.get("operational_status", "idle"),
        "current_operation_type": operation_state.get("current_operation_type"),
        "current_job_id": operation_state.get("current_job_id"),
        "current_queue_item_id": operation_state.get("current_queue_item_id"),
        "current_execution_id": operation_state.get("current_execution_id"),

        "compliance_status": compliance_status,
        "health_status": health_status,

        "compliance_issues": compliance_issues,
        "warnings": warnings,
        "errors": errors,
    }


def load_dashboard_base_data(
    session: Session,
) -> tuple[
    list[Repo],
    dict[str, AptlyMirrorState],
    dict[str, list[AptlySnapshotState]],
    list[AptlyPublishState],
]:
    repos = session.exec(select(Repo)).all()
    mirrors = session.exec(select(AptlyMirrorState)).all()
    snapshots = session.exec(select(AptlySnapshotState)).all()
    publishes = session.exec(select(AptlyPublishState)).all()

    mirrors_by_name = {
        mirror.name: mirror
        for mirror in mirrors
    }

    snapshots_by_source_mirror: dict[str, list[AptlySnapshotState]] = {}
    for snapshot in snapshots:
        if not snapshot.source_mirror_name:
            continue

        snapshots_by_source_mirror.setdefault(
            snapshot.source_mirror_name,
            [],
        ).append(snapshot)

    return repos, mirrors_by_name, snapshots_by_source_mirror, publishes


def build_all_repo_dashboard_items(session: Session) -> list[dict[str, Any]]:
    repos, mirrors_by_name, snapshots_by_source_mirror, publishes = load_dashboard_base_data(session)
    operation_states = get_repo_operation_states(
        session=session,
        repo_ids=[repo.id for repo in repos if repo.id is not None],
    )

    return [
        build_repo_dashboard_item(
            repo=repo,
            mirrors_by_name=mirrors_by_name,
            snapshots_by_source_mirror=snapshots_by_source_mirror,
            all_publishes=publishes,
            operation_state=operation_states.get(repo.id),
        )
        for repo in repos
    ]


def summarize_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    latest_update_at = get_latest_datetime(
        [item.get("latest_mirror_update_at") for item in items]
    )
    oldest_update_at = get_oldest_datetime(
        [item.get("latest_mirror_update_at") for item in items]
    )
    latest_snapshot_at = get_latest_datetime(
        [item.get("latest_snapshot_created_at") for item in items]
    )

    return {
        "repos_count": len(items),

        "healthy_count": count_items(items, "health_status", "healthy"),
        "warning_count": count_items(items, "health_status", "warning"),
        "critical_count": count_items(items, "health_status", "critical"),

        "compliant_count": count_items(items, "compliance_status", "compliant"),
        "non_compliant_count": count_items(items, "compliance_status", "non_compliant"),

        "running_count": count_items(items, "operational_status", "running"),
        "pending_count": count_items(items, "operational_status", "pending"),
        "failed_count": count_items(items, "operational_status", "failed"),

        "retention_ok_count": count_items(items, "retention_status", "ok"),
        "retention_exceeded_count": count_items(items, "retention_status", "exceeded"),

        "latest_update_at": latest_update_at,
        "oldest_update_at": oldest_update_at,
        "latest_snapshot_at": latest_snapshot_at,

        "status": aggregate_health_status(items),
        "compliance_status": aggregate_compliance_status(items),
        "operational_status": aggregate_operational_status(items),
    }


# ----------------------------
# Query / service functions
# ----------------------------

def get_dashboard_summary(session: Session) -> dict[str, Any]:
    repos, mirrors_by_name, snapshots_by_source_mirror, publishes = load_dashboard_base_data(session)
    operation_states = get_repo_operation_states(
        session=session,
        repo_ids=[repo.id for repo in repos if repo.id is not None],
    )

    snapshots = [
        snapshot
        for snapshot_group in snapshots_by_source_mirror.values()
        for snapshot in snapshot_group
    ]

    items = [
        build_repo_dashboard_item(
            repo=repo,
            mirrors_by_name=mirrors_by_name,
            snapshots_by_source_mirror=snapshots_by_source_mirror,
            all_publishes=publishes,
            operation_state=operation_states.get(repo.id),
        )
        for repo in repos
    ]

    providers = {item["provider"] for item in items}
    releases = {(item["provider"], item["release"]) for item in items}

    mirrors = list(mirrors_by_name.values())

    latest_aptly_sync_at = get_latest_datetime(
        [
            *[mirror.aptly_last_synced_at for mirror in mirrors],
            *[snapshot.aptly_last_synced_at for snapshot in snapshots],
            *[publish.aptly_last_synced_at for publish in publishes],
        ]
    )
    latest_config_sync_at = get_latest_datetime(
        [repo.updated_at for repo in repos]
    )
    latest_mirror_sync_at = get_latest_datetime(
        [mirror.aptly_last_synced_at for mirror in mirrors]
    )
    latest_snapshot_sync_at = get_latest_datetime(
        [snapshot.aptly_last_synced_at for snapshot in snapshots]
    )
    latest_published_snapshot_created_at = get_latest_datetime(
        [item.get("published_snapshot_created_at") for item in items]
    )
    latest_mirror_download_at = get_latest_datetime(
        [mirror.last_download_date for mirror in mirrors]
    )
    latest_snapshot_created_at = get_latest_datetime(
        [snapshot.created_at_aptly for snapshot in snapshots]
    )

    return {
        "providers_count": len(providers),
        "releases_count": len(releases),
        "repos_count": len(items),

        "healthy_count": count_items(items, "health_status", "healthy"),
        "warning_count": count_items(items, "health_status", "warning"),
        "critical_count": count_items(items, "health_status", "critical"),

        "compliant_count": count_items(items, "compliance_status", "compliant"),
        "non_compliant_count": count_items(items, "compliance_status", "non_compliant"),

        "running_count": count_items(items, "operational_status", "running"),
        "pending_count": count_items(items, "operational_status", "pending"),
        "failed_count": count_items(items, "operational_status", "failed"),

        "retention_ok_count": count_items(items, "retention_status", "ok"),
        "retention_exceeded_count": count_items(items, "retention_status", "exceeded"),

        "latest_aptly_sync_at": latest_aptly_sync_at,
        "latest_config_sync_at": latest_config_sync_at,
        "latest_mirror_sync_at": latest_mirror_sync_at,
        "latest_snapshot_sync_at": latest_snapshot_sync_at,
        "latest_published_snapshot_created_at": latest_published_snapshot_created_at,
        "latest_mirror_download_at": latest_mirror_download_at,
        "latest_snapshot_created_at": latest_snapshot_created_at,
        "is_inventory_stale": False,
    }


def get_dashboard_providers(session: Session) -> list[dict[str, Any]]:
    items = build_all_repo_dashboard_items(session)

    providers: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        providers.setdefault(item["provider"], []).append(item)

    result: list[dict[str, Any]] = []
    for provider, provider_items in providers.items():
        summary = summarize_items(provider_items)
        releases = {item["release"] for item in provider_items}

        result.append(
            {
                "provider": provider,
                "releases_count": len(releases),
                **summary,
            }
        )

    return sorted(result, key=lambda item: item["provider"])


def get_dashboard_provider_releases(
    session: Session,
    provider: str,
) -> list[dict[str, Any]]:
    items = [
        item
        for item in build_all_repo_dashboard_items(session)
        if item["provider"] == provider
    ]

    releases: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        releases.setdefault(item["release"], []).append(item)

    result: list[dict[str, Any]] = []
    for release, release_items in releases.items():
        summary = summarize_items(release_items)

        result.append(
            {
                "provider": provider,
                "release": release,
                "repo_names": [item["name"] for item in release_items],
                **summary,
                "warnings": [
                    warning
                    for item in release_items
                    for warning in item.get("warnings", [])
                ],
            }
        )

    return sorted(result, key=lambda item: item["release"])


def get_dashboard_provider_release_detail(
    session: Session,
    provider: str,
    release: str,
) -> dict[str, Any]:
    items = [
        item
        for item in build_all_repo_dashboard_items(session)
        if item["provider"] == provider and item["release"] == release
    ]

    if not items:
        raise HTTPException(
            status_code=404,
            detail=f"Release '{provider}/{release}' not found",
        )

    return {
        "provider": provider,
        "release": release,
        "summary": summarize_items(items),
        "repositories": items,
    }


def filter_dashboard_repository_items(
    items: list[dict[str, Any]],
    provider: str | None = None,
    release: str | None = None,
    health_status: str | None = None,
    compliance_status: str | None = None,
    operational_status: str | None = None,
    retention_status: str | None = None,
    only_non_compliant: bool = False,
    search: str | None = None,
) -> list[dict[str, Any]]:
    if provider:
        items = [item for item in items if item["provider"] == provider]

    if release:
        items = [item for item in items if item["release"] == release]

    if health_status:
        items = [item for item in items if item["health_status"] == health_status]

    if compliance_status:
        items = [item for item in items if item["compliance_status"] == compliance_status]

    if operational_status:
        items = [item for item in items if item["operational_status"] == operational_status]

    if retention_status:
        items = [item for item in items if item["retention_status"] == retention_status]

    if only_non_compliant:
        items = [
            item
            for item in items
            if item["compliance_status"] == "non_compliant"
        ]

    if search:
        search_lower = search.lower()
        items = [
            item
            for item in items
            if search_lower in item["name"].lower()
            or search_lower in item["effective_mirror_name"].lower()
        ]

    return items


def get_dashboard_repositories(
    session: Session,
    provider: str | None = None,
    release: str | None = None,
    health_status: str | None = None,
    compliance_status: str | None = None,
    operational_status: str | None = None,
    retention_status: str | None = None,
    only_non_compliant: bool = False,
    search: str | None = None,
) -> list[dict[str, Any]]:
    items = build_all_repo_dashboard_items(session)

    return filter_dashboard_repository_items(
        items=items,
        provider=provider,
        release=release,
        health_status=health_status,
        compliance_status=compliance_status,
        operational_status=operational_status,
        retention_status=retention_status,
        only_non_compliant=only_non_compliant,
        search=search,
    )


def get_dashboard_repository_by_name(
    session: Session,
    repo_name: str,
) -> dict[str, Any]:
    items = build_all_repo_dashboard_items(session)

    for item in items:
        if item["name"] == repo_name:
            return item

    raise HTTPException(
        status_code=404,
        detail=f"Repo '{repo_name}' not found",
    )


def get_dashboard_repository_by_id(
    session: Session,
    repo_id: int,
) -> dict[str, Any]:
    items = build_all_repo_dashboard_items(session)

    for item in items:
        if item["repo_id"] == repo_id:
            return item

    raise HTTPException(
        status_code=404,
        detail=f"Repo with id '{repo_id}' not found",
    )


def get_dashboard_compliance(
    session: Session,
    provider: str | None = None,
    release: str | None = None,
    issue_code: str | None = None,
) -> list[dict[str, Any]]:
    items = build_all_repo_dashboard_items(session)

    if provider:
        items = [item for item in items if item["provider"] == provider]

    if release:
        items = [item for item in items if item["release"] == release]

    items = [
        item
        for item in items
        if item["compliance_status"] == "non_compliant"
    ]

    if issue_code:
        items = [
            item
            for item in items
            if any(
                issue.get("code") == issue_code
                for issue in item.get("compliance_issues", [])
            )
        ]

    return [
        {
            "repo_id": item["repo_id"],
            "provider": item["provider"],
            "release": item["release"],
            "name": item["name"],
            "compliance_status": item["compliance_status"],
            "health_status": item["health_status"],
            "retention_status": item["retention_status"],
            "pipeline_status": item["pipeline_status"],
            "issues": item["compliance_issues"],
            "warnings": item["warnings"],
            "errors": item["errors"],
        }
        for item in items
    ]
