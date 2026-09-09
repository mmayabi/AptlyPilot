from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.clients.aptly_client import AptlyClient, TaskProgressCallback
from app.clients.aptly_desired_state import MirrorDesiredState


class ReconcileAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    SYNC = "sync"
    NOOP = "noop"


@dataclass(slots=True)
class ReconcileResult:
    mirror_name: str
    action: ReconcileAction
    changed_fields: list[str]
    result: dict[str, Any]


class MirrorReconciler:

    def __init__(self, aptly_client: AptlyClient):
        self.aptly = aptly_client

    def reconcile(
        self,
        desired: MirrorDesiredState,
        *,
        sync: bool = True,
        run_async: bool = True,
        wait: bool = False,
        force_update: bool = False,
        poll_interval: int = 5,
        max_wait_seconds: int = 3600,
        progress_callback: TaskProgressCallback | None = None,
    ) -> ReconcileResult:
        if not desired.enabled:
            return ReconcileResult(
                mirror_name=desired.name,
                action=ReconcileAction.NOOP,
                changed_fields=[],
                result={
                    "skipped": True,
                    "reason": "Mirror is disabled",
                },
            )

        actual = self.aptly.get_mirror(desired.name)

        if actual is None:
            result = self.aptly.create_mirror(
                mirror_name=desired.name,
                archive_url=desired.archive_url,
                distribution=desired.distribution,
                components=desired.components,
                architectures=desired.architectures,
                ignore_signatures=desired.ignore_signatures,
            )

            if sync:
                sync_result = self.aptly.update_mirror(
                    desired.name,
                    run_async=run_async,
                    wait=wait,
                    force_update=force_update,
                    ignore_signatures=desired.ignore_signatures,
                    skip_existing_packages=desired.skip_existing_packages,
                    max_tries=desired.max_tries,
                    poll_interval=poll_interval,
                    max_wait_seconds=max_wait_seconds,
                    progress_callback=progress_callback,
                )

                result = {
                    "create": result,
                    "sync": sync_result,
                }

            return ReconcileResult(
                mirror_name=desired.name,
                action=ReconcileAction.CREATE,
                changed_fields=[
                    "archive_url",
                    "distribution",
                    "components",
                    "architectures",
                    "ignore_signatures",
                ],
                result=result,
            )

        changed_fields = self._get_changed_fields(
            actual,
            desired,
        )

        if not changed_fields:
            if sync:
                sync_result = self.aptly.update_mirror(
                    desired.name,
                    run_async=run_async,
                    wait=wait,
                    force_update=force_update,
                    ignore_signatures=desired.ignore_signatures,
                    skip_existing_packages=desired.skip_existing_packages,
                    max_tries=desired.max_tries,
                    poll_interval=poll_interval,
                    max_wait_seconds=max_wait_seconds,
                    progress_callback=progress_callback,
                )

                return ReconcileResult(
                    mirror_name=desired.name,
                    action=ReconcileAction.SYNC,
                    changed_fields=[],
                    result=sync_result,
                )

            return ReconcileResult(
                mirror_name=desired.name,
                action=ReconcileAction.NOOP,
                changed_fields=[],
                result={},
            )

        result = self.aptly.update_mirror_config(
            mirror_name=desired.name,
            archive_url=desired.archive_url,
            distribution=desired.distribution,
            components=desired.components,
            architectures=desired.architectures,
            ignore_signatures=desired.ignore_signatures,
        )

        if sync:
            sync_result = self.aptly.update_mirror(
                desired.name,
                run_async=run_async,
                wait=wait,
                force_update=force_update,
                ignore_signatures=desired.ignore_signatures,
                skip_existing_packages=desired.skip_existing_packages,
                max_tries=desired.max_tries,
                poll_interval=poll_interval,
                max_wait_seconds=max_wait_seconds,
                progress_callback=progress_callback,
            )

            result = {
                "update": result,
                "sync": sync_result,
            }

        return ReconcileResult(
            mirror_name=desired.name,
            action=ReconcileAction.UPDATE,
            changed_fields=changed_fields,
            result=result,
        )

    @staticmethod
    def _get_changed_fields(
        actual: dict[str, Any],
        desired: MirrorDesiredState,
    ) -> list[str]:
        changed: list[str] = []

        if _normalize_url(actual.get("ArchiveRoot")) != _normalize_url(
            desired.archive_url
        ):
            changed.append("archive_url")

        if actual.get("Distribution") != desired.distribution:
            changed.append("distribution")

        if _normalize_list(actual.get("Components")) != _normalize_list(
            desired.components
        ):
            changed.append("components")

        if _normalize_list(actual.get("Architectures")) != _normalize_list(
            desired.architectures
        ):
            changed.append("architectures")

        if (
            "IgnoreSignatures" in actual
            and actual.get("IgnoreSignatures") != desired.ignore_signatures
        ):
            changed.append("ignore_signatures")

        return changed


def _normalize_url(value: Any) -> str:
    return str(value or "").rstrip("/")


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []

    return sorted(str(item) for item in value)
