from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


class AptlyMirrorState(SQLModel, table=True):
    """
    وضعیت واقعی mirrorهایی که از Aptly API خوانده شده‌اند.

    این جدول actual state است، نه desired/config.
    هر رکورد نماینده یک mirror موجود در Aptly است.
    """

    __tablename__ = "aptly_mirrors_state"
    __table_args__ = (
        UniqueConstraint("name", name="uq_aptly_mirror_state_name"),
    )

    id: int | None = Field(default=None, primary_key=True)

    # -------------------------
    # Aptly mirror fields
    # -------------------------
    uuid: str | None = Field(default=None, index=True)
    name: str = Field(index=True)

    archive_root: str | None = None
    distribution: str | None = Field(default=None, index=True)

    components: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )

    architectures: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )

    repo_meta: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )

    # تاریخ آخرین download/update از دید خود Aptly
    last_download_date: datetime | None = Field(default=None, index=True)

    filter: str | None = None
    status: int | None = None
    worker_pid: int | None = None

    filter_with_deps: bool = False
    skip_component_check: bool = False
    skip_architecture_check: bool = False
    download_sources: bool = False
    download_udebs: bool = False
    download_installer: bool = False

    # -------------------------
    # Local sync fields
    # -------------------------

    # آخرین زمانی که سیستم ما این mirror را از Aptly API خوانده است
    aptly_last_synced_at: datetime | None = Field(default=None, index=True)

    # success / failed
    aptly_last_sync_status: str | None = Field(default=None, index=True)

    aptly_last_sync_error: str | None = None

    # خروجی خام Aptly برای debug و future-proof بودن
    aptly_raw_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )

    item_created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    item_updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

class AptlySnapshotState(SQLModel, table=True):
    """
    Actual state of snapshots fetched from the Aptly API.

    Each record represents one snapshot currently available in Aptly.
    """

    __tablename__ = "aptly_snapshots_state"
    __table_args__ = (
        UniqueConstraint("name", name="uq_aptly_snapshot_state_name"),
    )

    id: int | None = Field(default=None, primary_key=True)

    # -------------------------
    # Aptly snapshot fields
    # -------------------------
    name: str = Field(index=True)

    created_at_aptly: datetime | None = Field(default=None, index=True)

    source_kind: str | None = Field(default=None, index=True)
    description: str | None = None

    origin: str | None = Field(default=None, index=True)

    not_automatic: str | None = None
    but_automatic_upgrades: str | None = None

    # Optional helper field extracted from description if possible.
    # Example:
    # Snapshot from mirror [debian-11-bullseye-security]: ...
    source_mirror_name: str | None = Field(default=None, index=True)

    # -------------------------
    # Local sync fields
    # -------------------------
    aptly_last_synced_at: datetime | None = Field(default=None, index=True)
    aptly_last_sync_status: str | None = Field(default=None, index=True)
    aptly_last_sync_error: str | None = None

    aptly_raw_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )

    item_created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    item_updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AptlyPublishState(SQLModel, table=True):
    """
    Actual state of published repositories fetched from the Aptly API.

    Each record represents one published repository entry currently available in Aptly.
    """

    __tablename__ = "aptly_publishes_state"
    __table_args__ = (
        UniqueConstraint(
            "storage",
            "prefix",
            "distribution",
            "source_kind",
            name="uq_aptly_publish_state_identity",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    # -------------------------
    # Aptly publish fields
    # -------------------------
    acquire_by_hash: bool = False

    architectures: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )

    but_automatic_upgrades: str | None = None
    codename: str | None = Field(default=None, index=True)
    distribution: str | None = Field(default=None, index=True)

    label: str | None = Field(default=None, index=True)

    multi_dist: bool = False

    not_automatic: str | None = None
    origin: str | None = Field(default=None, index=True)

    path: str | None = Field(default=None, index=True)
    prefix: str | None = Field(default=None, index=True)

    skip_contents: bool = False

    source_kind: str | None = Field(default=None, index=True)

    sources: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )

    # Helper fields extracted from Sources
    source_names: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )

    source_components: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )

    storage: str | None = Field(default=None, index=True)
    suite: str | None = Field(default=None, index=True)

    # -------------------------
    # Local sync fields
    # -------------------------
    aptly_last_synced_at: datetime | None = Field(default=None, index=True)
    aptly_last_sync_status: str | None = Field(default=None, index=True)
    aptly_last_sync_error: str | None = None

    aptly_raw_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )

    item_created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    item_updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )