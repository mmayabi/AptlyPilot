from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.api.deps import get_db_session
from app.core.permissions import require_viewer
from app.models.aptly_state import AptlyMirrorState, AptlyPublishState, AptlySnapshotState
from app.models.repo import Repo
from app.models.user import User

router = APIRouter(prefix="/aptly/dashboard", tags=["aptly-dashboard"])


# ----------------------------
# Config / thresholds
# ----------------------------

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
        key=lambda snapshot: as_aware_utc(snapshot.created_at_aptly) or datetime.min.replace(tzinfo=timezone.utc),
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
        key=lambda snapshot: as_aware_utc(snapshot.created_at_aptly) or datetime.min.replace(tzinfo=timezone.utc),
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


def build_repo_dashboard_item(
    repo: Repo,
    mirrors_by_name: dict[str, AptlyMirrorState],
    snapshots_by_source_mirror: dict[str, list[AptlySnapshotState]],
    all_publishes: list[AptlyPublishState],
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
        errors.append(
            {
                "code": "MIRROR_MISSING",
                "severity": "critical",
                "message": "Mirror is enabled in config but was not found in Aptly inventory",
            }
        )
        compliance_issues.append(
            {
                "code": "MIRROR_MISSING",
                "severity": "critical",
                "message": "Mirror is enabled in config but was not found in Aptly inventory",
            }
        )

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
        errors.append(
            {
                "code": "NO_SNAPSHOTS",
                "severity": "critical",
                "message": "Snapshot is enabled in config but no related snapshot was found",
            }
        )
        compliance_issues.append(
            {
                "code": "NO_SNAPSHOTS",
                "severity": "critical",
                "message": "Snapshot is enabled in config but no related snapshot was found",
            }
        )

    if retention_status == "exceeded":
        warnings.append(
            {
                "code": "RETENTION_EXCEEDED",
                "severity": "warning",
                "message": (
                    f"Snapshot retention exceeded: expected max "
                    f"{repo.retention_keep_last}, actual {len(snapshots)}"
                ),
                "expected": repo.retention_keep_last,
                "actual": len(snapshots),
            }
        )
        compliance_issues.append(
            {
                "code": "RETENTION_EXCEEDED",
                "severity": "warning",
                "message": (
                    f"Snapshot retention exceeded: expected max "
                    f"{repo.retention_keep_last}, actual {len(snapshots)}"
                ),
                "expected": repo.retention_keep_last,
                "actual": len(snapshots),
            }
        )

    if repo.publish_enabled and not related_publishes:
        errors.append(
            {
                "code": "PUBLISH_MISSING",
                "severity": "critical",
                "message": "Publish is enabled in config but no related publish entry was found",
            }
        )
        compliance_issues.append(
            {
                "code": "PUBLISH_MISSING",
                "severity": "critical",
                "message": "Publish is enabled in config but no related publish entry was found",
            }
        )

    if repo.publish_enabled and latest_snapshot and not latest_snapshot_is_published:
        warnings.append(
            {
                "code": "LATEST_SNAPSHOT_NOT_PUBLISHED",
                "severity": "warning",
                "message": "Latest snapshot is not published",
                "snapshot_name": latest_snapshot.name,
            }
        )
        compliance_issues.append(
            {
                "code": "LATEST_SNAPSHOT_NOT_PUBLISHED",
                "severity": "warning",
                "message": "Latest snapshot is not published",
                "snapshot_name": latest_snapshot.name,
            }
        )

    if mirror and latest_snapshot and not latest_mirror_has_snapshot:
        warnings.append(
            {
                "code": "LATEST_MIRROR_WITHOUT_SNAPSHOT",
                "severity": "warning",
                "message": "Latest mirror update does not have a corresponding snapshot",
                "latest_mirror_update_at": latest_mirror_update_at,
                "latest_snapshot_created_at": latest_snapshot_created_at,
            }
        )
        compliance_issues.append(
            {
                "code": "LATEST_MIRROR_WITHOUT_SNAPSHOT",
                "severity": "warning",
                "message": "Latest mirror update does not have a corresponding snapshot",
                "latest_mirror_update_at": latest_mirror_update_at,
                "latest_snapshot_created_at": latest_snapshot_created_at,
            }
        )

    if related_publishes and latest_published_snapshot and not publish_matches_latest_mirror_update:
        warnings.append(
            {
                "code": "PUBLISHED_SNAPSHOT_OUTDATED",
                "severity": "warning",
                "message": "Published snapshot is older than the latest mirror update",
                "latest_mirror_update_at": latest_mirror_update_at,
                "published_snapshot_created_at": latest_published_snapshot_created_at,
            }
        )
        compliance_issues.append(
            {
                "code": "PUBLISHED_SNAPSHOT_OUTDATED",
                "severity": "warning",
                "message": "Published snapshot is older than the latest mirror update",
                "latest_mirror_update_at": latest_mirror_update_at,
                "published_snapshot_created_at": latest_published_snapshot_created_at,
            }
        )

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

        # فعلاً تا وقتی Job/Operation را وصل نکرده‌ایم، idle می‌گذاریم.
        "operational_status": "idle",
        "current_operation_type": None,
        "current_job_id": None,

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

    return [
        build_repo_dashboard_item(
            repo=repo,
            mirrors_by_name=mirrors_by_name,
            snapshots_by_source_mirror=snapshots_by_source_mirror,
            all_publishes=publishes,
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
# Endpoints
# ----------------------------

@router.get("/summary")
def get_dashboard_summary_endpoint(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    items = build_all_repo_dashboard_items(session)

    providers = {item["provider"] for item in items}
    releases = {(item["provider"], item["release"]) for item in items}

    latest_aptly_sync_at = get_latest_datetime(
        [
            item.get("latest_mirror_update_at")
            for item in items
        ]
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

        "retention_ok_count": count_items(items, "retention_status", "ok"),
        "retention_exceeded_count": count_items(items, "retention_status", "exceeded"),

        "latest_aptly_sync_at": latest_aptly_sync_at,
        "is_inventory_stale": False,
    }


@router.get("/providers")
def get_dashboard_providers_endpoint(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
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


@router.get("/providers/{provider}/releases")
def get_dashboard_provider_releases_endpoint(
    provider: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
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


@router.get("/providers/{provider}/releases/{release}")
def get_dashboard_provider_release_detail_endpoint(
    provider: str,
    release: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
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


@router.get("/repositories")
def get_dashboard_repositories_endpoint(
    provider: str | None = Query(default=None),
    release: str | None = Query(default=None),
    health_status: str | None = Query(default=None),
    compliance_status: str | None = Query(default=None),
    operational_status: str | None = Query(default=None),
    retention_status: str | None = Query(default=None),
    only_non_compliant: bool = Query(default=False),
    search: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    items = build_all_repo_dashboard_items(session)

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


@router.get("/repositories/by-name/{repo_name}")
def get_dashboard_repository_by_name_endpoint(
    repo_name: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    items = build_all_repo_dashboard_items(session)

    for item in items:
        if item["name"] == repo_name:
            return item

    raise HTTPException(
        status_code=404,
        detail=f"Repo '{repo_name}' not found",
    )


@router.get("/repositories/{repo_id}")
def get_dashboard_repository_by_id_endpoint(
    repo_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    items = build_all_repo_dashboard_items(session)

    for item in items:
        if item["repo_id"] == repo_id:
            return item

    raise HTTPException(
        status_code=404,
        detail=f"Repo with id '{repo_id}' not found",
    )


@router.get("/compliance")
def get_dashboard_compliance_endpoint(
    provider: str | None = Query(default=None),
    release: str | None = Query(default=None),
    issue_code: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
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