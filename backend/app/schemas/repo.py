from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class MirrorDefaultsConfig(BaseModel):
    enabled: bool = True
    ignore_signatures: bool = False
    max_tries: int = 3

    @field_validator("max_tries")
    @classmethod
    def validate_max_tries(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_tries must be >= 1")
        return value


class MirrorConfig(BaseModel):
    enabled: bool | None = None
    archive_url: str
    distribution: str
    components: list[str]
    architectures: list[str]
    ignore_signatures: bool | None = None
    max_tries: int | None = None

    @field_validator("components", "architectures")
    @classmethod
    def validate_non_empty_list(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("max_tries")
    @classmethod
    def validate_max_tries(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("max_tries must be >= 1")
        return value


class SnapshotConfig(BaseModel):
    enabled: bool = True
    naming: str = "{name}-{timestamp}"
    timestamp_format: str = "%Y%m%d-%H%M"


class PublishDefaultsConfig(BaseModel):
    enabled: bool = True
    endpoint: str = "filesystem:repo"
    gpg_key: str | None = None
    skip_signing: bool = False
    acquire_by_hash: bool = True
    skip_bz2: bool = True
    skip_contents: bool = True


class PublishConfig(BaseModel):
    enabled: bool | None = None
    endpoint: str | None = None
    gpg_key: str | None = None
    skip_signing: bool | None = None
    acquire_by_hash: bool | None = None
    skip_bz2: bool | None = None
    skip_contents: bool | None = None
    prefix: str | None = None
    distribution: str | None = None
    components: list[str] = Field(default_factory=list)
    architectures: list[str] = Field(default_factory=list)
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
    def validate_keep_last(cls, value: int) -> int:
        if value < 1:
            raise ValueError("keep_last must be >= 1")
        return value


class ScheduleType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ScheduleConfig(BaseModel):
    enabled: bool = True
    type: ScheduleType = ScheduleType.DAILY


class DefaultsConfig(BaseModel):
    mirror: MirrorDefaultsConfig = Field(default_factory=MirrorDefaultsConfig)
    snapshot: SnapshotConfig = Field(default_factory=SnapshotConfig)
    publish: PublishDefaultsConfig = Field(default_factory=PublishDefaultsConfig)
    test: TestConfig = Field(default_factory=TestConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)


class RepoItemConfig(BaseModel):
    """
    One Aptly repository item under:
    repos -> provider -> release -> repo_name
    """

    mirror_name: str | None = None
    mirror: MirrorConfig
    snapshot: SnapshotConfig | None = None
    publish: PublishConfig | None = None
    test: TestConfig | None = None
    retention: RetentionConfig | None = None
    schedule: ScheduleConfig | None = None


class ReposConfigFile(BaseModel):
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)

    # provider -> release -> repo_name -> RepoItemConfig
    repos: dict[str, dict[str, dict[str, RepoItemConfig]]]

    @field_validator("repos")
    @classmethod
    def validate_repos_not_empty(
        cls,
        value: dict[str, dict[str, dict[str, RepoItemConfig]]],
    ) -> dict[str, dict[str, dict[str, RepoItemConfig]]]:
        if not value:
            raise ValueError("repos must not be empty")
        return value

    @model_validator(mode="after")
    def validate_nested_repos_not_empty(self) -> "ReposConfigFile":
        for provider, releases in self.repos.items():
            if not releases:
                raise ValueError(f"provider '{provider}' must contain at least one release")
            for release, repos in releases.items():
                if not repos:
                    raise ValueError(f"provider '{provider}', release '{release}' must contain at least one repo")
        return self


class ResolvedRepoConfig(BaseModel):
    provider: str
    release: str
    name: str
    mirror_name: str | None = None
    mirror: MirrorConfig
    snapshot: SnapshotConfig
    publish: PublishConfig
    test: TestConfig
    retention: RetentionConfig
    schedule: ScheduleConfig
    raw_config: dict[str, Any]


class RepoRead(BaseModel):
    id: int
    name: str
    mirror_name: str | None = None
    provider: str
    release: str

    mirror_enabled: bool
    snapshot_enabled: bool
    publish_enabled: bool
    test_enabled: bool

    mirror: MirrorConfig
    snapshot: SnapshotConfig
    publish: PublishConfig
    test: TestConfig
    retention: RetentionConfig
    schedule: ScheduleConfig

    raw_config: dict[str, Any]

    created_at: datetime
    updated_at: datetime


class RepoConfigRead(BaseModel):
    name: str
    provider: str
    release: str
    raw_config: dict[str, Any]


class ConfigValidationResponse(BaseModel):
    valid: bool
    repo_count: int
    repos: list[str]
    errors: list[str] = Field(default_factory=list)


class RepoSyncItemResult(BaseModel):
    name: str
    provider: str
    release: str
    action: str


class RepoSyncResponse(BaseModel):
    created: int
    updated: int
    disabled: int = 0
    total: int
    repos: list[RepoSyncItemResult]
