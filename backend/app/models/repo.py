from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class Repo(SQLModel, table=True):
    __tablename__ = "repos"

    id: int | None = Field(default=None, primary_key=True)

    # Logical identity in AptlyPilot / YAML / API
    name: str = Field(index=True, unique=True, nullable=False)

    # Real Aptly mirror name.
    # If null, service should use `name` as effective mirror name.
    mirror_name: str | None = Field(default=None, index=True)

    # YAML grouping:
    # repos -> provider -> release -> repo_name
    provider: str = Field(index=True, nullable=False)
    release: str = Field(index=True, nullable=False)

    # Operation enable flags from resolved config
    mirror_enabled: bool = Field(default=True)
    snapshot_enabled: bool = Field(default=True)
    publish_enabled: bool = Field(default=True)
    test_enabled: bool = Field(default=True)

    # -------------------------
    # Mirror config
    # -------------------------
    mirror_archive_url: str = Field(nullable=False)
    mirror_distribution: str = Field(nullable=False)

    mirror_components: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
    )
    mirror_architectures: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
    )

    mirror_ignore_signatures: bool = Field(default=False)
    mirror_max_tries: int = Field(default=1)

    # -------------------------
    # Snapshot config
    # -------------------------
    snapshot_naming: str = Field(default="{name}-{timestamp}")
    snapshot_timestamp_format: str = Field(default="%Y%m%d-%H%M")

    # -------------------------
    # Publish config
    # -------------------------
    publish_endpoint: str | None = None
    publish_prefix: str | None = None
    publish_distribution: str | None = None

    publish_components: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
    )
    publish_architectures: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
    )

    publish_label: str | None = None
    publish_origin: str | None = None
    publish_codename: str | None = None
    publish_suite: str | None = None

    publish_acquire_by_hash: bool = Field(default=True)
    publish_skip_bz2: bool = Field(default=True)
    publish_skip_contents: bool = Field(default=True)
    publish_skip_signing: bool = Field(default=False)
    publish_gpg_key: str | None = None

    # -------------------------
    # Test config
    # -------------------------
    test_checks: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
    )

    # -------------------------
    # Retention config
    # -------------------------
    retention_keep_last: int = Field(default=7)

    # Full resolved config after merging defaults + repo override.
    raw_config: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )

    # DB row metadata only
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)