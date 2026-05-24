from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

# -----------------------------
# Mirrors
# -----------------------------
class AptlyMirrorStateRead(BaseModel):
    id: int

    uuid: str | None
    name: str

    archive_root: str | None
    distribution: str | None

    components: list[str]
    architectures: list[str]

    repo_meta: dict[str, Any]

    last_download_date: datetime | None

    filter: str | None
    status: int | None
    worker_pid: int | None

    filter_with_deps: bool
    skip_component_check: bool
    skip_architecture_check: bool
    download_sources: bool
    download_udebs: bool
    download_installer: bool

    aptly_last_synced_at: datetime | None
    aptly_last_sync_status: str | None
    aptly_last_sync_error: str | None

    item_created_at: datetime
    item_updated_at: datetime

    class Config:
        from_attributes = True


class AptlyMirrorSyncResult(BaseModel):
    resource_type: str
    status: str
    synced_at: datetime
    total_items: int
    created: int
    updated: int
    deleted: int
    skipped: int


class AptlyMirrorInventorySummary(BaseModel):
    resource_type: str

    total: int
    failed: int

    latest_synced_at: datetime | None
    oldest_synced_at: datetime | None

class AptlyMirrorStateDetailRead(AptlyMirrorStateRead):
    aptly_raw_data: dict[str, Any]

# -----------------------------
# Snapshots
# -----------------------------
class AptlySnapshotStateRead(BaseModel):
    id: int

    name: str

    created_at_aptly: datetime | None

    source_kind: str | None
    description: str | None

    origin: str | None

    not_automatic: str | None
    but_automatic_upgrades: str | None

    source_mirror_name: str | None

    aptly_last_synced_at: datetime | None
    aptly_last_sync_status: str | None
    aptly_last_sync_error: str | None

    item_created_at: datetime
    item_updated_at: datetime

    class Config:
        from_attributes = True


class AptlySnapshotStateDetailRead(AptlySnapshotStateRead):
    aptly_raw_data: dict[str, Any]


class AptlySnapshotSyncResult(BaseModel):
    resource_type: str
    status: str
    synced_at: datetime
    total_items: int
    created: int
    updated: int
    deleted: int
    skipped: int


class AptlySnapshotInventorySummary(BaseModel):
    resource_type: str

    total: int
    failed: int

    latest_synced_at: datetime | None
    oldest_synced_at: datetime | None

    latest_snapshot_created_at: datetime | None
    oldest_snapshot_created_at: datetime | None

# -----------------------------
# Publish
# -----------------------------
class AptlyPublishStateRead(BaseModel):
    id: int

    acquire_by_hash: bool

    architectures: list[str]

    but_automatic_upgrades: str | None
    codename: str | None
    distribution: str | None

    label: str | None
    multi_dist: bool

    not_automatic: str | None
    origin: str | None

    path: str | None
    prefix: str | None

    skip_contents: bool
    source_kind: str | None

    sources: list[dict[str, Any]]

    source_names: list[str]
    source_components: list[str]

    storage: str | None
    suite: str | None

    aptly_last_synced_at: datetime | None
    aptly_last_sync_status: str | None
    aptly_last_sync_error: str | None

    item_created_at: datetime
    item_updated_at: datetime

    class Config:
        from_attributes = True


class AptlyPublishStateDetailRead(AptlyPublishStateRead):
    aptly_raw_data: dict[str, Any]


class AptlyPublishSyncResult(BaseModel):
    resource_type: str
    status: str
    synced_at: datetime
    total_items: int
    created: int
    updated: int
    deleted: int
    skipped: int


class AptlyPublishInventorySummary(BaseModel):
    resource_type: str

    total: int
    failed: int

    snapshot_based: int
    repo_based: int

    unique_prefixes: list[str]
    unique_distributions: list[str]

    latest_synced_at: datetime | None
    oldest_synced_at: datetime | None

# -----------------------------
# SYNC ALL
# -----------------------------
class AptlyInventorySyncResult(BaseModel):
    resource_type: str
    status: str
    started_at: datetime
    finished_at: datetime
    results: dict[str, Any]
    errors: list[dict[str, str]]