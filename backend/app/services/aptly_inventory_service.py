from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.clients.aptly_client import AptlyClient
from app.models.aptly_state import AptlyMirrorState, AptlySnapshotState, AptlyPublishState

# -----------------------------
# Helpers/mapper
# -----------------------------
def parse_aptly_datetime(value: str | None) -> datetime | None:
    """
    Aptly ممکن است تاریخ را با nanosecond بدهد، مثل:

    2026-04-05T11:10:57.373007411Z

    اما datetime پایتون microsecond یعنی 6 رقم را قبول می‌کند.
    """

    if not value:
        return None

    value = value.strip()

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    if "." in value:
        prefix, rest = value.split(".", 1)

        frac = rest
        tz = ""

        for sep in ["+", "-"]:
            idx = frac.find(sep)
            if idx != -1:
                tz = frac[idx:]
                frac = frac[:idx]
                break

        frac = frac[:6].ljust(6, "0")
        value = f"{prefix}.{frac}{tz}"

    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return None


def extract_source_mirror_name_from_snapshot_description(
    description: str | None,
) -> str | None:
    if not description:
        return None

    prefix = "Snapshot from mirror ["
    if description.startswith(prefix):
        rest = description[len(prefix):]
        end_index = rest.find("]")

        if end_index != -1:
            source_name = rest[:end_index].strip()
            return source_name or None

    match = re.search(r"\bfrom mirror\s+\[?([^\]\s:]+)\]?", description)
    if match:
        return match.group(1).strip() or None

    return None

def build_publish_identity(payload: dict[str, Any]) -> tuple[str, str, str, str]:
    """
    Build a stable identity for a published repository entry.

    Aptly publish entries do not have a UUID.
    We identify them using:
    storage + prefix + distribution + source_kind
    """

    storage = payload.get("Storage") or ""
    prefix = payload.get("Prefix") or ""
    distribution = payload.get("Distribution") or ""
    source_kind = payload.get("SourceKind") or ""

    return storage, prefix, distribution, source_kind


def extract_publish_source_names(sources: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []

    for source in sources:
        name = source.get("Name")
        if name and name not in names:
            names.append(name)

    return names


def extract_publish_source_components(sources: list[dict[str, Any]]) -> list[str]:
    components: list[str] = []

    for source in sources:
        component = source.get("Component")
        if component and component not in components:
            components.append(component)

    return components

# -----------------------------
# Mirrors
# -----------------------------
def apply_mirror_payload(
    mirror_state: AptlyMirrorState,
    payload: dict[str, Any],
    synced_at: datetime,
) -> AptlyMirrorState:
    mirror_state.uuid = payload.get("UUID")
    mirror_state.name = payload.get("Name")

    mirror_state.archive_root = payload.get("ArchiveRoot")
    mirror_state.distribution = payload.get("Distribution")

    mirror_state.components = payload.get("Components") or []
    mirror_state.architectures = payload.get("Architectures") or []

    mirror_state.repo_meta = payload.get("Meta") or {}

    mirror_state.last_download_date = parse_aptly_datetime(
        payload.get("LastDownloadDate")
    )

    mirror_state.filter = payload.get("Filter") or ""
    mirror_state.status = payload.get("Status")
    mirror_state.worker_pid = payload.get("WorkerPID")

    mirror_state.filter_with_deps = bool(payload.get("FilterWithDeps", False))
    mirror_state.skip_component_check = bool(payload.get("SkipComponentCheck", False))
    mirror_state.skip_architecture_check = bool(
        payload.get("SkipArchitectureCheck", False)
    )
    mirror_state.download_sources = bool(payload.get("DownloadSources", False))
    mirror_state.download_udebs = bool(payload.get("DownloadUdebs", False))
    mirror_state.download_installer = bool(payload.get("DownloadInstaller", False))

    mirror_state.aptly_last_synced_at = synced_at
    mirror_state.aptly_last_sync_status = "success"
    mirror_state.aptly_last_sync_error = None

    mirror_state.aptly_raw_data = payload
    mirror_state.item_updated_at = synced_at

    return mirror_state

def sync_aptly_mirrors(
    session: Session,
    aptly_client: AptlyClient,
) -> dict[str, Any]:
    """
    mirrorها را از Aptly API می‌خواند و جدول aptly_mirrors_state را sync می‌کند.

    منبع:
    GET /api/mirrors

    نکته:
    mirrorهایی که دیگر در خروجی Aptly نیستند از دیتابیس حذف می‌شوند.
    """

    synced_at = datetime.now(timezone.utc)

    mirrors_payload = aptly_client.list_mirrors()

    seen_names: set[str] = set()
    created_count = 0
    updated_count = 0
    skipped_count = 0

    for payload in mirrors_payload:
        name = payload.get("Name")
        if not name:
            skipped_count += 1
            continue

        seen_names.add(name)

        mirror_state = session.exec(
            select(AptlyMirrorState).where(
                AptlyMirrorState.name == name
            )
        ).first()

        if mirror_state:
            updated_count += 1
        else:
            mirror_state = AptlyMirrorState(name=name)
            session.add(mirror_state)
            created_count += 1

        apply_mirror_payload(
            mirror_state=mirror_state,
            payload=payload,
            synced_at=synced_at,
        )

    deleted_count = 0

    existing_mirrors = session.exec(
        select(AptlyMirrorState)
    ).all()

    for mirror_state in existing_mirrors:
        if mirror_state.name not in seen_names:
            session.delete(mirror_state)
            deleted_count += 1

    session.commit()

    return {
        "resource_type": "mirrors",
        "status": "success",
        "synced_at": synced_at,
        "total_items": len(mirrors_payload),
        "created": created_count,
        "updated": updated_count,
        "deleted": deleted_count,
        "skipped": skipped_count,
    }


def get_mirrors_inventory_summary(session: Session) -> dict[str, Any]:
    """
    خلاصه وضعیت mirrorها از روی دیتابیس local.
    """

    all_mirrors = session.exec(
        select(AptlyMirrorState)
    ).all()

    total = len(all_mirrors)

    synced_values = [
        mirror.aptly_last_synced_at
        for mirror in all_mirrors
        if mirror.aptly_last_synced_at is not None
    ]

    latest_synced_at = max(synced_values) if synced_values else None
    oldest_synced_at = min(synced_values) if synced_values else None

    failed_count = len(
        [
            mirror
            for mirror in all_mirrors
            if mirror.aptly_last_sync_status == "failed"
        ]
    )

    return {
        "resource_type": "mirrors",
        "total": total,
        "failed": failed_count,
        "latest_synced_at": latest_synced_at,
        "oldest_synced_at": oldest_synced_at,
    }

# -----------------------------
# Snapshots
# -----------------------------
def apply_snapshot_payload(
    snapshot_state: AptlySnapshotState,
    payload: dict[str, Any],
    synced_at: datetime,
) -> AptlySnapshotState:
    snapshot_state.name = payload.get("Name")

    snapshot_state.created_at_aptly = parse_aptly_datetime(
        payload.get("CreatedAt")
    )

    snapshot_state.source_kind = payload.get("SourceKind")
    snapshot_state.description = payload.get("Description")
    snapshot_state.origin = payload.get("Origin")

    snapshot_state.not_automatic = payload.get("NotAutomatic")
    snapshot_state.but_automatic_upgrades = payload.get("ButAutomaticUpgrades")

    snapshot_state.source_mirror_name = (
        extract_source_mirror_name_from_snapshot_description(
            snapshot_state.description
        )
    )

    snapshot_state.aptly_last_synced_at = synced_at
    snapshot_state.aptly_last_sync_status = "success"
    snapshot_state.aptly_last_sync_error = None

    snapshot_state.aptly_raw_data = payload
    snapshot_state.item_updated_at = synced_at

    return snapshot_state

def sync_aptly_snapshots(
    session: Session,
    aptly_client: AptlyClient,
) -> dict[str, Any]:
    """
    Fetch snapshots from the Aptly API and sync the local snapshot inventory.

    Source:
    GET /api/snapshots

    Since we do not keep an exists_in_aptly flag, snapshots that no longer
    appear in the latest Aptly response are deleted from the local database.
    """

    synced_at = datetime.now(timezone.utc)

    snapshots_payload = aptly_client.list_snapshots()

    seen_names: set[str] = set()
    created_count = 0
    updated_count = 0
    skipped_count = 0

    for payload in snapshots_payload:
        name = payload.get("Name")
        if not name:
            skipped_count += 1
            continue

        seen_names.add(name)

        snapshot_state = session.exec(
            select(AptlySnapshotState).where(
                AptlySnapshotState.name == name
            )
        ).first()

        if snapshot_state:
            updated_count += 1
        else:
            snapshot_state = AptlySnapshotState(name=name)
            session.add(snapshot_state)
            created_count += 1

        apply_snapshot_payload(
            snapshot_state=snapshot_state,
            payload=payload,
            synced_at=synced_at,
        )

    deleted_count = 0

    existing_snapshots = session.exec(
        select(AptlySnapshotState)
    ).all()

    for snapshot_state in existing_snapshots:
        if snapshot_state.name not in seen_names:
            session.delete(snapshot_state)
            deleted_count += 1

    session.commit()

    return {
        "resource_type": "snapshots",
        "status": "success",
        "synced_at": synced_at,
        "total_items": len(snapshots_payload),
        "created": created_count,
        "updated": updated_count,
        "deleted": deleted_count,
        "skipped": skipped_count,
    }

def get_snapshots_inventory_summary(session: Session) -> dict[str, Any]:
    """
    Return snapshot inventory summary from the local database.
    """

    all_snapshots = session.exec(
        select(AptlySnapshotState)
    ).all()

    total = len(all_snapshots)

    synced_values = [
        snapshot.aptly_last_synced_at
        for snapshot in all_snapshots
        if snapshot.aptly_last_synced_at is not None
    ]

    created_values = [
        snapshot.created_at_aptly
        for snapshot in all_snapshots
        if snapshot.created_at_aptly is not None
    ]

    latest_synced_at = max(synced_values) if synced_values else None
    oldest_synced_at = min(synced_values) if synced_values else None

    latest_snapshot_created_at = max(created_values) if created_values else None
    oldest_snapshot_created_at = min(created_values) if created_values else None

    failed_count = len(
        [
            snapshot
            for snapshot in all_snapshots
            if snapshot.aptly_last_sync_status == "failed"
        ]
    )

    return {
        "resource_type": "snapshots",
        "total": total,
        "failed": failed_count,
        "latest_synced_at": latest_synced_at,
        "oldest_synced_at": oldest_synced_at,
        "latest_snapshot_created_at": latest_snapshot_created_at,
        "oldest_snapshot_created_at": oldest_snapshot_created_at,
    }

# -----------------------------
# Publish
# -----------------------------
def apply_publish_payload(
    publish_state: AptlyPublishState,
    payload: dict[str, Any],
    synced_at: datetime,
) -> AptlyPublishState:
    sources = payload.get("Sources") or []

    publish_state.acquire_by_hash = bool(payload.get("AcquireByHash", False))
    publish_state.architectures = payload.get("Architectures") or []

    publish_state.but_automatic_upgrades = payload.get("ButAutomaticUpgrades")
    publish_state.codename = payload.get("Codename")
    publish_state.distribution = payload.get("Distribution")

    publish_state.label = payload.get("Label")
    publish_state.multi_dist = bool(payload.get("MultiDist", False))

    publish_state.not_automatic = payload.get("NotAutomatic")
    publish_state.origin = payload.get("Origin")

    publish_state.path = payload.get("Path")
    publish_state.prefix = payload.get("Prefix")

    publish_state.skip_contents = bool(payload.get("SkipContents", False))
    publish_state.source_kind = payload.get("SourceKind")

    publish_state.sources = sources
    publish_state.source_names = extract_publish_source_names(sources)
    publish_state.source_components = extract_publish_source_components(sources)

    publish_state.storage = payload.get("Storage")
    publish_state.suite = payload.get("Suite")

    publish_state.aptly_last_synced_at = synced_at
    publish_state.aptly_last_sync_status = "success"
    publish_state.aptly_last_sync_error = None

    publish_state.aptly_raw_data = payload
    publish_state.item_updated_at = synced_at

    return publish_state

def sync_aptly_publishes(
    session: Session,
    aptly_client: AptlyClient,
) -> dict[str, Any]:
    """
    Fetch published repositories from the Aptly API and sync the local publish inventory.

    Source:
    GET /api/publish

    Since we do not keep an exists_in_aptly flag, publish entries that no longer
    appear in the latest Aptly response are deleted from the local database.
    """

    synced_at = datetime.now(timezone.utc)

    publishes_payload = aptly_client.list_publishes()

    seen_identities: set[tuple[str, str, str, str]] = set()
    created_count = 0
    updated_count = 0
    skipped_count = 0

    for payload in publishes_payload:
        storage, prefix, distribution, source_kind = build_publish_identity(payload)

        if not prefix or not distribution:
            skipped_count += 1
            continue

        identity = (storage, prefix, distribution, source_kind)
        seen_identities.add(identity)

        publish_state = session.exec(
            select(AptlyPublishState).where(
                AptlyPublishState.storage == storage,
                AptlyPublishState.prefix == prefix,
                AptlyPublishState.distribution == distribution,
                AptlyPublishState.source_kind == source_kind,
            )
        ).first()

        if publish_state:
            updated_count += 1
        else:
            publish_state = AptlyPublishState(
                storage=storage,
                prefix=prefix,
                distribution=distribution,
                source_kind=source_kind,
            )
            session.add(publish_state)
            created_count += 1

        apply_publish_payload(
            publish_state=publish_state,
            payload=payload,
            synced_at=synced_at,
        )

    deleted_count = 0

    existing_publishes = session.exec(
        select(AptlyPublishState)
    ).all()

    for publish_state in existing_publishes:
        identity = (
            publish_state.storage or "",
            publish_state.prefix or "",
            publish_state.distribution or "",
            publish_state.source_kind or "",
        )

        if identity not in seen_identities:
            session.delete(publish_state)
            deleted_count += 1

    session.commit()

    return {
        "resource_type": "publishes",
        "status": "success",
        "synced_at": synced_at,
        "total_items": len(publishes_payload),
        "created": created_count,
        "updated": updated_count,
        "deleted": deleted_count,
        "skipped": skipped_count,
    }

def get_publishes_inventory_summary(session: Session) -> dict[str, Any]:
    """
    Return published repository inventory summary from the local database.
    """

    all_publishes = session.exec(
        select(AptlyPublishState)
    ).all()

    total = len(all_publishes)

    synced_values = [
        publish.aptly_last_synced_at
        for publish in all_publishes
        if publish.aptly_last_synced_at is not None
    ]

    latest_synced_at = max(synced_values) if synced_values else None
    oldest_synced_at = min(synced_values) if synced_values else None

    failed_count = len(
        [
            publish
            for publish in all_publishes
            if publish.aptly_last_sync_status == "failed"
        ]
    )

    snapshot_based_count = len(
        [
            publish
            for publish in all_publishes
            if publish.source_kind == "snapshot"
        ]
    )

    repo_based_count = len(
        [
            publish
            for publish in all_publishes
            if publish.source_kind == "repo"
        ]
    )

    unique_prefixes = sorted(
        {
            publish.prefix
            for publish in all_publishes
            if publish.prefix
        }
    )

    unique_distributions = sorted(
        {
            publish.distribution
            for publish in all_publishes
            if publish.distribution
        }
    )

    return {
        "resource_type": "publishes",
        "total": total,
        "failed": failed_count,
        "snapshot_based": snapshot_based_count,
        "repo_based": repo_based_count,
        "unique_prefixes": unique_prefixes,
        "unique_distributions": unique_distributions,
        "latest_synced_at": latest_synced_at,
        "oldest_synced_at": oldest_synced_at,
    }

# -----------------------------
# SYNC ALL
# -----------------------------
def sync_aptly_inventory(
    session: Session,
    aptly_client: AptlyClient,
) -> dict[str, Any]:
    """
    Sync all Aptly inventory resources into the local database.

    Resources:
    - mirrors
    - snapshots
    - publishes
    """

    started_at = datetime.now(timezone.utc)

    results: dict[str, Any] = {}
    overall_status = "success"
    errors: list[dict[str, str]] = []

    sync_steps = [
        ("mirrors", sync_aptly_mirrors),
        ("snapshots", sync_aptly_snapshots),
        ("publishes", sync_aptly_publishes),
    ]

    for resource_type, sync_func in sync_steps:
        try:
            results[resource_type] = sync_func(
                session=session,
                aptly_client=aptly_client,
            )
        except Exception as exc:
            overall_status = "partial_failed"
            errors.append(
                {
                    "resource_type": resource_type,
                    "error": str(exc),
                }
            )

            results[resource_type] = {
                "resource_type": resource_type,
                "status": "failed",
                "error": str(exc),
            }

    finished_at = datetime.now(timezone.utc)

    return {
        "resource_type": "inventory",
        "status": overall_status,
        "started_at": started_at,
        "finished_at": finished_at,
        "results": results,
        "errors": errors,
    }
