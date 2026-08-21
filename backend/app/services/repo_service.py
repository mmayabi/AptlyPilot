import hashlib
from datetime import UTC, datetime, timedelta
from copy import deepcopy
from typing import Any

from sqlmodel import Session, select

from app.models.job import Job, JobDefinitionStatus, JobStep
from app.models.job_schedule import JobSchedule, JobScheduleStatus, JobScheduleType
from app.models.repo import Repo
from app.models.template import JobStepTemplate, JobTemplate
from app.repositories.repo_repo import (
    create_repo,
    get_repo_by_name,
    list_repos,
    list_repos_by_provider,
    list_repos_by_provider_release,
    save_repo,
)
from app.schemas.repo import (
    ConfigValidationResponse,
    DefaultsConfig,
    MirrorConfig,
    PublishConfig,
    RepoConfigRead,
    RepoItemConfig,
    RepoRead,
    RepoSyncItemResult,
    RepoSyncResponse,
    ResolvedRepoConfig,
    RetentionConfig,
    ScheduleConfig,
    ScheduleType,
    SnapshotConfig,
    TestConfig,
)
from app.services.config_loader_service import (
    load_and_validate_repos_config,
    validate_repos_config,
)

PIPELINE_TEMPLATE_NAME = "aptly.repository.pipeline"


def _merge_model(default_data: dict[str, Any], override_model) -> dict[str, Any]:
    merged = deepcopy(default_data)
    if override_model is not None:
        merged.update(override_model.model_dump(mode="json", exclude_none=True))
    return merged


def validate_resolved_repo_config(
    repo_name: str,
    mirror: MirrorConfig,
    publish: PublishConfig,
) -> None:
    if mirror.enabled is True:
        if not mirror.archive_url:
            raise ValueError(f"{repo_name}: mirror.archive_url is required")
        if not mirror.distribution:
            raise ValueError(f"{repo_name}: mirror.distribution is required")
        if not mirror.components:
            raise ValueError(f"{repo_name}: mirror.components must not be empty")
        if not mirror.architectures:
            raise ValueError(f"{repo_name}: mirror.architectures must not be empty")

    if publish.enabled is True:
        required_fields = {
            "publish.prefix": publish.prefix,
            "publish.distribution": publish.distribution,
            "publish.components": publish.components,
            "publish.architectures": publish.architectures,
        }
        missing = [field for field, value in required_fields.items() if not value]
        if missing:
            raise ValueError(
                f"{repo_name}: missing required publish fields: {', '.join(missing)}"
            )


def merge_repo_config(
    provider: str,
    release: str,
    repo_name: str,
    defaults: DefaultsConfig,
    repo_config: RepoItemConfig,
) -> ResolvedRepoConfig:
    mirror_data = _merge_model(
        defaults.mirror.model_dump(mode="json"),
        repo_config.mirror,
    )
    mirror = MirrorConfig.model_validate(mirror_data)

    snapshot_data = _merge_model(
        defaults.snapshot.model_dump(mode="json"),
        repo_config.snapshot,
    )
    snapshot = SnapshotConfig.model_validate(snapshot_data)

    publish_data = _merge_model(
        defaults.publish.model_dump(mode="json"),
        repo_config.publish,
    )
    publish = PublishConfig.model_validate(publish_data)

    test_data = _merge_model(
        defaults.test.model_dump(mode="json"),
        repo_config.test,
    )
    test = TestConfig.model_validate(test_data)

    retention_data = _merge_model(
        defaults.retention.model_dump(mode="json"),
        repo_config.retention,
    )
    retention = RetentionConfig.model_validate(retention_data)

    schedule_data = _merge_model(
        defaults.schedule.model_dump(mode="json"),
        repo_config.schedule,
    )
    schedule = ScheduleConfig.model_validate(schedule_data)

    validate_resolved_repo_config(repo_name, mirror, publish)

    raw_config = {
        "provider": provider,
        "release": release,
        "name": repo_name,
        "mirror_name": repo_config.mirror_name,
        "mirror": mirror.model_dump(mode="json"),
        "snapshot": snapshot.model_dump(mode="json"),
        "publish": publish.model_dump(mode="json"),
        "test": test.model_dump(mode="json"),
        "retention": retention.model_dump(mode="json"),
        "schedule": schedule.model_dump(mode="json"),
    }

    return ResolvedRepoConfig(
        provider=provider,
        release=release,
        name=repo_name,
        mirror_name=repo_config.mirror_name,
        mirror=mirror,
        snapshot=snapshot,
        publish=publish,
        test=test,
        retention=retention,
        schedule=schedule,
        raw_config=raw_config,
    )


def flatten_repos_config(config_file) -> list[ResolvedRepoConfig]:
    flattened: list[ResolvedRepoConfig] = []

    for provider, releases in config_file.repos.items():
        for release, repos in releases.items():
            for repo_name, repo_config in repos.items():
                flattened.append(
                    merge_repo_config(
                        provider=provider,
                        release=release,
                        repo_name=repo_name,
                        defaults=config_file.defaults,
                        repo_config=repo_config,
                    )
                )

    return flattened


def repo_to_read(repo: Repo) -> RepoRead:
    raw = repo.raw_config or {}

    mirror = MirrorConfig.model_validate(raw.get("mirror", {}))
    snapshot = SnapshotConfig.model_validate(raw.get("snapshot", {}))
    publish = PublishConfig.model_validate(raw.get("publish", {}))
    test = TestConfig.model_validate(raw.get("test", {}))
    retention = RetentionConfig.model_validate(raw.get("retention", {}))
    schedule = ScheduleConfig.model_validate(raw.get("schedule", {}))

    return RepoRead(
        id=repo.id,
        name=repo.name,
        mirror_name=repo.mirror_name,
        provider=repo.provider,
        release=repo.release,
        mirror_enabled=repo.mirror_enabled,
        snapshot_enabled=repo.snapshot_enabled,
        publish_enabled=repo.publish_enabled,
        test_enabled=repo.test_enabled,
        mirror=mirror,
        snapshot=snapshot,
        publish=publish,
        test=test,
        retention=retention,
        schedule=schedule,
        raw_config=repo.raw_config,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


def get_all_repos(session: Session) -> list[Repo]:
    return list_repos(session)


def get_repos_by_provider(session: Session, provider: str) -> list[Repo]:
    return list_repos_by_provider(session, provider)


def get_repos_by_provider_release(session: Session, provider: str, release: str) -> list[Repo]:
    return list_repos_by_provider_release(session, provider, release)


def get_repo_or_none(session: Session, repo_name: str) -> Repo | None:
    return get_repo_by_name(session, repo_name)


def get_repo_config(session: Session, repo_name: str) -> RepoConfigRead | None:
    repo = get_repo_by_name(session, repo_name)
    if repo is None:
        return None
    return RepoConfigRead(
        name=repo.name,
        provider=repo.provider,
        release=repo.release,
        raw_config=repo.raw_config,
    )


def validate_config_file() -> ConfigValidationResponse:
    return validate_repos_config()


def _apply_resolved_config_to_repo(repo: Repo, resolved: ResolvedRepoConfig) -> Repo:
    mirror = resolved.mirror
    snapshot = resolved.snapshot
    publish = resolved.publish
    test = resolved.test
    retention = resolved.retention

    repo.name = resolved.name
    repo.mirror_name = resolved.mirror_name
    repo.provider = resolved.provider
    repo.release = resolved.release

    repo.mirror_enabled = bool(mirror.enabled)
    repo.snapshot_enabled = bool(snapshot.enabled)
    repo.publish_enabled = bool(publish.enabled)
    repo.test_enabled = bool(test.enabled)

    repo.mirror_archive_url = mirror.archive_url
    repo.mirror_distribution = mirror.distribution
    repo.mirror_components = mirror.components
    repo.mirror_architectures = mirror.architectures
    repo.mirror_ignore_signatures = bool(mirror.ignore_signatures)
    repo.mirror_max_tries = int(mirror.max_tries or 1)

    repo.snapshot_naming = snapshot.naming
    repo.snapshot_timestamp_format = snapshot.timestamp_format

    repo.publish_endpoint = publish.endpoint
    repo.publish_prefix = publish.prefix
    repo.publish_distribution = publish.distribution
    repo.publish_components = publish.components
    repo.publish_architectures = publish.architectures
    repo.publish_label = publish.label
    repo.publish_origin = publish.origin
    repo.publish_codename = publish.codename
    repo.publish_suite = publish.suite
    repo.publish_acquire_by_hash = bool(publish.acquire_by_hash)
    repo.publish_skip_bz2 = bool(publish.skip_bz2)
    repo.publish_skip_contents = bool(publish.skip_contents)
    repo.publish_skip_signing = bool(publish.skip_signing)
    repo.publish_gpg_key = publish.gpg_key

    repo.test_checks = test.checks
    repo.retention_keep_last = retention.keep_last
    repo.raw_config = resolved.raw_config
    repo.updated_at = datetime.now(UTC).replace(tzinfo=None)

    return repo


def get_pipeline_template(session: Session) -> JobTemplate:
    template = session.exec(
        select(JobTemplate).where(JobTemplate.name == PIPELINE_TEMPLATE_NAME)
    ).first()

    if template is None:
        raise RuntimeError(
            f"Default pipeline template not found: {PIPELINE_TEMPLATE_NAME}"
        )

    return template


def get_template_steps(
    session: Session,
    template_id: int,
) -> list[JobStepTemplate]:
    return list(
        session.exec(
            select(JobStepTemplate)
            .where(JobStepTemplate.template_id == template_id)
            .order_by(JobStepTemplate.order, JobStepTemplate.id)
        ).all()
    )


def ensure_pipeline_job_for_repo(
    session: Session,
    repo: Repo,
) -> Job:
    template = get_pipeline_template(session)

    job = session.exec(
        select(Job).where(
            Job.repo_id == repo.id,
            Job.template_id == template.id,
        )
    ).first()

    if job is None:
        job = Job(
            template_id=template.id,
            repo_id=repo.id,
            status=JobDefinitionStatus.ACTIVE,
            created_by_user_id=None,
        )
        session.add(job)
        session.flush()

    template_steps = get_template_steps(session, template.id)
    existing_steps = session.exec(
        select(JobStep).where(JobStep.job_id == job.id)
    ).all()
    existing_by_template_step_id = {
        step.step_template_id: step
        for step in existing_steps
    }
    template_step_ids = {step.id for step in template_steps}

    for step in existing_steps:
        if step.step_template_id not in template_step_ids:
            session.delete(step)

    for template_step in template_steps:
        existing_step = existing_by_template_step_id.get(template_step.id)

        if existing_step:
            existing_step.script_id = template_step.script_id
            existing_step.order = template_step.order
            session.add(existing_step)
            continue

        session.add(
            JobStep(
                job_id=job.id,
                step_template_id=template_step.id,
                script_id=template_step.script_id,
                order=template_step.order,
                params={},
            )
        )

    job.status = JobDefinitionStatus.ACTIVE
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(job)
    session.flush()

    return job


def get_schedule_type(schedule: ScheduleConfig) -> JobScheduleType:
    if schedule.type == ScheduleType.MONTHLY:
        return JobScheduleType.MONTHLY

    if schedule.type == ScheduleType.WEEKLY:
        return JobScheduleType.WEEKLY

    return JobScheduleType.DAILY


def stable_repo_offset(repo_name: str) -> int:
    digest = hashlib.sha256(repo_name.encode("utf-8")).hexdigest()

    return int(digest[:12], 16)


def compute_next_config_run_at(
    repo_name: str,
    schedule_type: JobScheduleType,
    now: datetime | None = None,
) -> datetime:
    if now is None:
        now = datetime.utcnow()

    offset = stable_repo_offset(repo_name)
    minute_of_day = offset % 1440
    hour = minute_of_day // 60
    minute = minute_of_day % 60

    if schedule_type == JobScheduleType.WEEKLY:
        day_of_week = (offset // 1440) % 7
        days_ahead = (day_of_week - now.weekday()) % 7
        candidate = (
            now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            + timedelta(days=days_ahead)
        )

        if candidate <= now:
            candidate += timedelta(weeks=1)

        return candidate

    if schedule_type == JobScheduleType.MONTHLY:
        day_of_month = ((offset // 1440) % 28) + 1
        candidate = now.replace(
            day=day_of_month,
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        if candidate <= now:
            if candidate.month == 12:
                candidate = candidate.replace(year=candidate.year + 1, month=1)
            else:
                candidate = candidate.replace(month=candidate.month + 1)

        return candidate

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if candidate <= now:
        candidate += timedelta(days=1)

    return candidate


def get_schedule_for_job(
    session: Session,
    job_id: int,
) -> JobSchedule | None:
    return session.exec(
        select(JobSchedule)
        .where(JobSchedule.job_id == job_id)
        .order_by(JobSchedule.id)
    ).first()


def ensure_config_schedule_for_job(
    session: Session,
    *,
    repo: Repo,
    job: Job,
    schedule_config: ScheduleConfig,
) -> JobSchedule | None:
    existing_schedule = get_schedule_for_job(session, job.id)

    if not schedule_config.enabled:
        if existing_schedule:
            existing_schedule.status = JobScheduleStatus.DISABLED
            existing_schedule.updated_at = datetime.utcnow()
            session.add(existing_schedule)

        return existing_schedule

    schedule_type = get_schedule_type(schedule_config)
    next_run_at = compute_next_config_run_at(
        repo_name=repo.name,
        schedule_type=schedule_type,
    )

    if existing_schedule is None:
        existing_schedule = JobSchedule(
            job_id=job.id,
            schedule_type=schedule_type,
            status=JobScheduleStatus.ENABLED,
            next_run_at=next_run_at,
            created_by_user_id=None,
        )
        session.add(existing_schedule)
        return existing_schedule

    type_changed = existing_schedule.schedule_type != schedule_type
    is_disabled = existing_schedule.status == JobScheduleStatus.DISABLED
    is_due_or_past = existing_schedule.next_run_at <= datetime.utcnow()

    existing_schedule.schedule_type = schedule_type
    existing_schedule.status = JobScheduleStatus.ENABLED

    if type_changed or is_disabled or is_due_or_past:
        existing_schedule.next_run_at = next_run_at

    existing_schedule.updated_at = datetime.utcnow()
    session.add(existing_schedule)

    return existing_schedule


def sync_repos_from_config(session: Session) -> RepoSyncResponse:
    config_file = load_and_validate_repos_config()
    flattened_repos = flatten_repos_config(config_file)

    created = 0
    updated = 0
    results: list[RepoSyncItemResult] = []

    for resolved in flattened_repos:
        existing_repo = get_repo_by_name(session, resolved.name)

        if existing_repo is None:
            repo = Repo(
                name=resolved.name,
                provider=resolved.provider,
                release=resolved.release,
                mirror_archive_url=resolved.mirror.archive_url,
                mirror_distribution=resolved.mirror.distribution,
            )
            repo = _apply_resolved_config_to_repo(repo, resolved)
            repo = create_repo(session, repo)
            job = ensure_pipeline_job_for_repo(session, repo)
            ensure_config_schedule_for_job(
                session=session,
                repo=repo,
                job=job,
                schedule_config=resolved.schedule,
            )
            session.commit()
            created += 1
            results.append(
                RepoSyncItemResult(
                    name=resolved.name,
                    provider=resolved.provider,
                    release=resolved.release,
                    action="created",
                )
            )
            continue

        repo = _apply_resolved_config_to_repo(existing_repo, resolved)
        repo = save_repo(session, repo)
        job = ensure_pipeline_job_for_repo(session, repo)
        ensure_config_schedule_for_job(
            session=session,
            repo=repo,
            job=job,
            schedule_config=resolved.schedule,
        )
        session.commit()
        updated += 1
        results.append(
            RepoSyncItemResult(
                name=resolved.name,
                provider=resolved.provider,
                release=resolved.release,
                action="updated",
            )
        )

    return RepoSyncResponse(
        created=created,
        updated=updated,
        total=len(flattened_repos),
        repos=results,
    )
