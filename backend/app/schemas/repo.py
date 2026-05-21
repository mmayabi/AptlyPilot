from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator
from app.models.repo import RepoStatus


class MirrorConfig(BaseModel):
    archive_url: str
    distribution: str
    components: list[str]
    architectures: list[str]

    @field_validator("components", "architectures")
    @classmethod
    def validate_non_empty_list(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("must not be empty")
        return v


class SnapshotConfig(BaseModel):
    enabled: bool = True
    naming: str = "{name}-{timestamp}"
    timestamp_format: str = "%Y%m%d-%H%M"


class PublishConfig(BaseModel):
    enabled: bool = False
    endpoint: str | None = None
    gpg_key: str | None = None
    skip_signing: bool = False
    acquire_by_hash: bool = True
    skip_bz2: bool = True
    skip_contents: bool = True
    prefix: str | None = None
    distribution: str | None = None
    components: list[str] = Field(default_factory=list)
    label: str | None = None
    origin: str | None = None
    codename: str | None = None
    suite: str | None = None


class TestConfig(BaseModel):
    enabled: bool = True
    checks: list[str] = Field(default_factory=list)


class RetentionConfig(BaseModel):
    keep_last: int = 7

    @field_validator("keep_last")
    @classmethod
    def validate_keep_last(cls, v: int) -> int:
        if v < 1:
            raise ValueError("keep_last must be >=1")
        return v


class DefaultsConfig(BaseModel):
    snapshot: SnapshotConfig = Field(default_factory=SnapshotConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)
    test: TestConfig = Field(default_factory=TestConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)


class RepoConfig(BaseModel):
    enabled: bool = True
    mirror: MirrorConfig
    snapshot: SnapshotConfig | None = None
    publish: PublishConfig | None = None
    test: TestConfig | None = None
    retention: RetentionConfig | None = None


class ReposConfigFile(BaseModel):
    defaults: DefaultsConfig | None = None
    repos: dict[str, RepoConfig]

    @field_validator("repos")
    @classmethod
    def validate_repos_not_empty(cls, v: dict[str, RepoConfig]) -> dict[str, RepoConfig]:
        if not v:
            raise ValueError("repos must not be empty")
        return v


class RepoRead(BaseModel):
    id: int
    name: str
    mirror_name: str
    enabled: bool

    mirror: MirrorConfig
    snapshot: SnapshotConfig
    publish: PublishConfig
    test: TestConfig
    retention: RetentionConfig

    status: RepoStatus
    last_sync_status: str | None = None
    last_sync_at: datetime | None = None
    last_error: str | None = None

    created_at: datetime
    updated_at: datetime


class RepoConfigRead(BaseModel):
    name: str
    raw_config: dict[str, Any]


class ConfigValidationResponse(BaseModel):
    valid: bool
    repo_count: int
    repos: list[str]
    errors: list[str] = Field(default_factory=list)


class RepoSyncItemResult(BaseModel):
    name: str
    action: str


class RepoSyncResponse(BaseModel):
    created: int
    updated: int
    total: int
    repos: list[RepoSyncItemResult]