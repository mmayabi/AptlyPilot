from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.repo import Repo


# ============================================================
# Mirror
# ============================================================

class MirrorDesiredState(BaseModel):
    """
    Effective desired state of an Aptly mirror.
    """

    name: str

    enabled: bool = True

    archive_url: str
    distribution: str

    components: list[str] = Field(
        default_factory=list,
    )

    architectures: list[str] = Field(
        default_factory=list,
    )

    ignore_signatures: bool = False
    max_tries: int = 3
    skip_existing_packages: bool | None = None


def build_mirror_desired_state_from_repo(repo: Repo) -> MirrorDesiredState:
    return MirrorDesiredState(
        name=repo.mirror_name or repo.name,
        enabled=repo.mirror_enabled,
        archive_url=repo.mirror_archive_url,
        distribution=repo.mirror_distribution,
        components=repo.mirror_components,
        architectures=repo.mirror_architectures,
        ignore_signatures=repo.mirror_ignore_signatures,
        max_tries=repo.mirror_max_tries,
    )


# ============================================================
# Snapshot
# ============================================================

class SnapshotDesiredState(BaseModel):
    """
    Effective desired state of an Aptly snapshot.
    """

    name: str

    enabled: bool = True

    source_mirror_name: str

    naming: str = "{name}-{timestamp}"

    timestamp_format: str = "%Y%m%d-%H%M"

    description: str | None = None


# ============================================================
# Publish
# ============================================================

class PublishDesiredState(BaseModel):
    """
    Effective desired state of an Aptly published repository.
    """

    enabled: bool = True

    storage: str = "filesystem:repository"

    prefix: str
    distribution: str

    components: list[str] = Field(
        default_factory=list,
    )

    architectures: list[str] = Field(
        default_factory=list,
    )

    label: str | None = None
    origin: str | None = None
    codename: str | None = None
    suite: str | None = None

    gpg_key: str | None = None

    skip_signing: bool = False
    acquire_by_hash: bool = True
    skip_bz2: bool = True
    skip_contents: bool = True
