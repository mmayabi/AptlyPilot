from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import requests


class AptlyAPIError(Exception):
    pass


SUCCESS_TASK_STATES = {
    "success",
    "succeeded",
    "done",
    "completed",
    "complete",
    "finished",
}
FAILED_TASK_STATES = {
    "failed",
    "failure",
    "error",
    "errored",
    "canceled",
    "cancelled",
}
DEFAULT_TERMINAL_TASK_STATES = {2, 3}
TaskProgressCallback = Callable[[dict[str, Any]], None]


class AptlyClient:
    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        timeout: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.auth = (username, password) if username and password else None
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        return headers

    def request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._headers(),
                auth=self.auth,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise AptlyAPIError(f"Cannot connect to Aptly API: {exc}") from exc

        if response.status_code >= 400:
            raise AptlyAPIError(
                f"Aptly API error {response.status_code}: {response.text}"
            )

        if not response.text:
            return None

        try:
            return response.json()
        except ValueError as exc:
            raise AptlyAPIError(
                f"Aptly API returned non-json response: {response.text[:300]}"
            ) from exc

    def get_version(self):
        return self.request("GET", "/api/version")

    def list_mirrors(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/api/mirrors")

        if data is None:
            return []

        if not isinstance(data, list):
            raise AptlyAPIError("Unexpected response from /api/mirrors. Expected list.")

        return data

    def list_snapshots(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/api/snapshots")

        if data is None:
            return []

        if not isinstance(data, list):
            raise AptlyAPIError("Unexpected response from /api/snapshots. Expected list.")

        return data

    def list_publishes(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/api/publish")

        if data is None:
            return []

        if not isinstance(data, list):
            raise AptlyAPIError("Unexpected response from /api/publish. Expected list.")

        return data

    # -----------------------------
    # Task helpers
    # -----------------------------

    def get_task(self, task_id: int | str) -> dict[str, Any]:
        data = self.request("GET", f"/api/tasks/{task_id}")

        if not isinstance(data, dict):
            raise AptlyAPIError(f"Unexpected response from /api/tasks/{task_id}")

        return data

    def get_task_detail(self, task_id: int | str) -> Any:
        return self.request("GET", f"/api/tasks/{task_id}/detail")

    def get_task_return_value(self, task_id: int | str) -> Any:
        return self.request("GET", f"/api/tasks/{task_id}/return_value")

    def get_task_output(self, task_id: int | str) -> str:
        data = self.request("GET", f"/api/tasks/{task_id}/output")

        if data is None:
            return ""

        if isinstance(data, str):
            return data

        return str(data)

    def wait_task(
        self,
        task_id: int | str,
        poll_interval: int = 5,
        max_wait_seconds: int = 3600,
        terminal_states: set[int] | None = None,
        progress_callback: TaskProgressCallback | None = None,
    ) -> dict[str, Any]:
        if terminal_states is None:
            terminal_states = DEFAULT_TERMINAL_TASK_STATES

        started_at = time.monotonic()

        while True:
            task = self.get_task(task_id)
            state = self._extract_task_state(task)
            detail = self._get_task_detail_safely(task_id)
            output = self._get_task_output_safely(task_id)

            self._emit_task_progress(
                progress_callback=progress_callback,
                payload={
                    "task_id": task_id,
                    "task": task,
                    "detail": detail,
                    "output": output,
                },
            )

            if self._task_has_failed(task):
                return_value = self.get_task_return_value(task_id)
                raise AptlyAPIError(
                    f"Aptly task {task_id} failed. State: {state}. "
                    f"Return value: {return_value}. Output:\n{output}"
                )

            if self._task_has_succeeded(task, terminal_states):
                return_value = self.get_task_return_value(task_id)

                result = {
                    "task_id": task_id,
                    "task": task,
                    "detail": detail,
                    "return_value": return_value,
                    "output": output,
                }

                if isinstance(return_value, dict):
                    code = return_value.get("Code")
                    if code is not None and int(code) >= 400:
                        raise AptlyAPIError(
                            f"Aptly task {task_id} failed with code {code}:\n{output}"
                        )
                elif isinstance(return_value, int):
                    if return_value != 0:
                        raise AptlyAPIError(
                            f"Aptly task {task_id} failed with code {return_value}:\n{output}"
                        )

                return result

            if time.monotonic() - started_at > max_wait_seconds:
                raise AptlyAPIError(
                    f"Timeout waiting for Aptly task {task_id}. Last task state: {task}"
                )

            time.sleep(poll_interval)

    def _emit_task_progress(
        self,
        *,
        progress_callback: TaskProgressCallback | None,
        payload: dict[str, Any],
    ) -> None:
        if progress_callback is None:
            return

        progress_callback(payload)

    def _get_task_detail_safely(self, task_id: int | str) -> Any:
        try:
            return self.get_task_detail(task_id)
        except AptlyAPIError as exc:
            return {
                "error": str(exc),
            }

    def _get_task_output_safely(self, task_id: int | str) -> str:
        try:
            return self.get_task_output(task_id)
        except AptlyAPIError as exc:
            return f"Could not fetch task output: {exc}"

    def _extract_task_state(self, task: dict[str, Any]) -> Any:
        for key in ("State", "state", "Status", "status"):
            if key in task:
                return task[key]
        return None

    def _normalize_task_state(self, state: Any) -> str:
        return str(state).strip().lower()

    def _task_has_failed(self, task: dict[str, Any]) -> bool:
        for key in ("Error", "error", "Err", "err", "Failure", "failure"):
            if task.get(key):
                return True

        return self._normalize_task_state(
            self._extract_task_state(task)
        ) in FAILED_TASK_STATES

    def _task_has_succeeded(
        self,
        task: dict[str, Any],
        terminal_states: set[int],
    ) -> bool:
        for key in ("Done", "done", "Finished", "finished"):
            if task.get(key) is True:
                return True

        state = self._extract_task_state(task)
        if isinstance(state, int):
            return state in terminal_states

        normalized_state = self._normalize_task_state(state)
        if normalized_state in SUCCESS_TASK_STATES:
            return True

        if normalized_state.isdigit():
            return int(normalized_state) in terminal_states

        return False

    # -----------------------------
    # Mirror update
    # -----------------------------
    def update_mirror(
        self,
        mirror_name: str,
        *,
        run_async: bool = False,
        wait: bool = True,
        force_update: bool = False,
        ignore_signatures: bool | None = None,
        skip_existing_packages: bool | None = None,
        max_tries: int | None = None,
        poll_interval: int = 5,
        max_wait_seconds: int = 3600,
        progress_callback: TaskProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        اجرای mirror update.

        حالت‌ها:
        1. run_async=False
           درخواست به شکل sync اجرا می‌شود و Aptly همان‌جا منتظر پایان update می‌ماند.

        2. run_async=True, wait=False
           Aptly task را background اجرا می‌کند و فقط task_id برمی‌گردد.

        3. run_async=True, wait=True
           task به شکل async در Aptly شروع می‌شود، اما این متد خودش task را poll می‌کند
           و بعد از پایان نتیجه، output و return_value را برمی‌گرداند.
        """

        safe_name = quote(mirror_name, safe="")
        params: dict[str, str] = {}

        if run_async:
            params["_async"] = "1"

        body: dict[str, Any] = {}

        if force_update:
            body["ForceUpdate"] = True

        if ignore_signatures is not None:
            body["IgnoreSignatures"] = ignore_signatures

        if skip_existing_packages is not None:
            body["SkipExistingPackages"] = skip_existing_packages

        if max_tries is not None:
            body["MaxTries"] = max_tries

        data = self.request(
            "PUT",
            f"/api/mirrors/{safe_name}",
            params=params,
            json=body,
        )

        if not run_async:
            return {
                "mode": "sync",
                "mirror_name": mirror_name,
                "result": data,
            }

        task_id = self._extract_task_id(data)

        if not wait:
            return {
                "mode": "async",
                "mirror_name": mirror_name,
                "task_id": task_id,
                "task": data,
            }

        task_result = self.wait_task(
            task_id=task_id,
            poll_interval=poll_interval,
            max_wait_seconds=max_wait_seconds,
            progress_callback=progress_callback,
        )

        return {
            "mode": "async_wait",
            "mirror_name": mirror_name,
            **task_result,
        }

    def _extract_task_id(self, data: Any) -> int | str:
        """
        استخراج task id از پاسخ Aptly.

        بسته به نسخه/پیاده‌سازی Aptly، پاسخ async ممکن است یکی از این شکل‌ها باشد:
        {"ID": 123, ...}
        {"TaskID": 123}
        123
        """

        if isinstance(data, int):
            return data

        if isinstance(data, str) and data.strip():
            return data

        if isinstance(data, dict):
            for key in ("ID", "TaskID", "task_id", "id"):
                if key in data:
                    return data[key]

        raise AptlyAPIError(f"Cannot extract task id from Aptly response: {data}")

    def _extract_task_id_or_none(self, data: Any) -> int | str | None:
        try:
            return self._extract_task_id(data)
        except AptlyAPIError:
            return None

    def _wait_task_response_if_present(
        self,
        data: Any,
        *,
        poll_interval: int = 5,
        max_wait_seconds: int = 3600,
        progress_callback: TaskProgressCallback | None = None,
    ) -> dict[str, Any] | None:
        task_id = self._extract_task_id_or_none(data)
        if task_id is None:
            return None

        return self.wait_task(
            task_id=task_id,
            poll_interval=poll_interval,
            max_wait_seconds=max_wait_seconds,
            progress_callback=progress_callback,
        )
    
    # -----------------------------
    # Snapshot Create from Mirror
    # -----------------------------
    def get_snapshot(self, snapshot_name: str) -> dict[str, Any]:
        safe_name = quote(snapshot_name, safe="")
        data = self.request("GET", f"/api/snapshots/{safe_name}")

        if not isinstance(data, dict):
            raise AptlyAPIError(
                f"Unexpected response from /api/snapshots/{snapshot_name}. Expected dict."
            )

        return data

    def snapshot_exists(self, snapshot_name: str) -> bool:
        try:
            self.get_snapshot(snapshot_name)
            return True
        except AptlyAPIError as exc:
            if "404" in str(exc):
                return False
            raise

    def create_snapshot_from_mirror(
        self,
        mirror_name: str,
        snapshot_name: str,
        *,
        description: str | None = None,
        fail_if_exists: bool = True,
        run_async: bool = False,
        wait: bool = True,
        poll_interval: int = 5,
        max_wait_seconds: int = 3600,
        progress_callback: TaskProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        ساخت snapshot از mirror.

        معادل CLI:

            aptly snapshot create <snapshot_name> from mirror <mirror_name>

        پارامتر fail_if_exists:
        - اگر True باشد و snapshot از قبل وجود داشته باشد، خطا می‌دهد.
        - اگر False باشد و snapshot وجود داشته باشد، همان snapshot موجود را برمی‌گرداند.
        """

        if self.snapshot_exists(snapshot_name):
            existing_snapshot = self.get_snapshot(snapshot_name)

            if fail_if_exists:
                raise AptlyAPIError(
                    f"Snapshot already exists: {snapshot_name}"
                )

            return {
                "mode": "exists",
                "mirror_name": mirror_name,
                "snapshot_name": snapshot_name,
                "snapshot": existing_snapshot,
                "created": False,
            }

        safe_mirror_name = quote(mirror_name, safe="")

        params: dict[str, str] = {}
        if run_async:
            params["_async"] = "1"

        body: dict[str, Any] = {
            "Name": snapshot_name,
        }

        if description:
            body["Description"] = description

        try:
            data = self.request(
                "POST",
                f"/api/mirrors/{safe_mirror_name}/snapshots",
                params=params,
                json=body,
            )
        except AptlyAPIError as exc:
            # برای حالت race condition:
            # ممکن است بین snapshot_exists و POST، یک worker دیگر snapshot را ساخته باشد.
            if "already exists" in str(exc).lower() or "409" in str(exc):
                if fail_if_exists:
                    raise AptlyAPIError(
                        f"Snapshot already exists: {snapshot_name}"
                    ) from exc

                existing_snapshot = self.get_snapshot(snapshot_name)

                return {
                    "mode": "exists",
                    "mirror_name": mirror_name,
                    "snapshot_name": snapshot_name,
                    "snapshot": existing_snapshot,
                    "created": False,
                }

            raise

        if not run_async:
            return {
                "mode": "sync",
                "mirror_name": mirror_name,
                "snapshot_name": snapshot_name,
                "snapshot": data,
                "created": True,
            }

        task_id = self._extract_task_id(data)

        if not wait:
            return {
                "mode": "async",
                "mirror_name": mirror_name,
                "snapshot_name": snapshot_name,
                "task_id": task_id,
                "task": data,
                "created": None,
            }

        task_result = self.wait_task(
            task_id=task_id,
            poll_interval=poll_interval,
            max_wait_seconds=max_wait_seconds,
            progress_callback=progress_callback,
        )

        return {
            "mode": "async_wait",
            "mirror_name": mirror_name,
            "snapshot_name": snapshot_name,
            "created": True,
            **task_result,
        }

    def delete_snapshot(
        self,
        snapshot_name: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Delete a snapshot from Aptly.

        Equivalent to:

            aptly snapshot drop <snapshot_name>
        """

        safe_name = quote(snapshot_name, safe="")
        params: dict[str, str] = {}

        if force:
            params["force"] = "1"

        data = self.request(
            "DELETE",
            f"/api/snapshots/{safe_name}",
            params=params,
        )

        return {
            "snapshot_name": snapshot_name,
            "deleted": True,
            "result": data,
        }

    # -----------------------------
    # Publish
    # -----------------------------
    def _encode_publish_prefix(self, prefix: str | None) -> str:
        """
        تبدیل publish prefix به فرم قابل استفاده در URL مربوط به Aptly.

        طبق مستندات Aptly:
        - root prefix باید با :. مشخص شود.
        - اگر prefix شامل / باشد، باید / به _ تبدیل شود.
        - اگر prefix شامل _ باشد، باید _ به __ تبدیل شود.

        مثال‌ها:
            "." یا "" یا None  -> ":."
            "debian/security" -> "debian_security"
            "my_repo"         -> "my__repo"
            "filesystem:repo" -> "filesystem:repo"
        """

        if prefix is None or prefix == "" or prefix == ".":
            return ":."

        # ترتیب مهم است: اول underscore را escape می‌کنیم، بعد slash را تبدیل می‌کنیم.
        encoded = prefix.replace("_", "__").replace("/", "_")

        return quote(encoded, safe=":")

    def _build_publish_api_prefix(
        self,
        *,
        storage: str | None = None,
        prefix: str | None = ".",
    ) -> str | None:
        normalized_prefix = prefix or "."

        if storage:
            return f"{storage}:{normalized_prefix}"

        return normalized_prefix

    def _find_publish(
        self,
        *,
        prefix: str | None,
        distribution: str,
        storage: str | None = None,
    ) -> dict[str, Any] | None:
        """
        publish موجود را از خروجی /api/publish پیدا می‌کند.

        چون GET /api/publish/:prefix/:distribution در مستندات legacy به شکل واضح
        نیامده، امن‌ترین راه این است که list_publishes را بگیریم و فیلتر کنیم.
        """

        normalized_prefix = prefix or "."

        for item in self.list_publishes():
            item_prefix = item.get("Prefix") or "."
            item_distribution = item.get("Distribution")
            item_storage = item.get("Storage")

            if (
                item_prefix == normalized_prefix
                and item_distribution == distribution
                and (storage is None or item_storage == storage)
            ):
                return item

        return None

    def _value_contains_snapshot_name(self, value: Any, snapshot_name: str) -> bool:
        if value == snapshot_name:
            return True

        if isinstance(value, dict):
            return any(
                self._value_contains_snapshot_name(item, snapshot_name)
                for item in value.values()
            )

        if isinstance(value, list):
            return any(
                self._value_contains_snapshot_name(item, snapshot_name)
                for item in value
            )

        return False

    def _get_verified_snapshot_publish(
        self,
        *,
        prefix: str | None,
        distribution: str,
        storage: str | None,
        snapshot_name: str,
    ) -> dict[str, Any]:
        publish = self._find_publish(
            prefix=prefix,
            distribution=distribution,
            storage=storage,
        )

        if publish is None:
            raise AptlyAPIError(
                f"Published repository was not found after publish operation: "
                f"prefix={prefix or '.'}, distribution={distribution}, "
                f"snapshot={snapshot_name}"
            )

        if not self._value_contains_snapshot_name(publish, snapshot_name):
            raise AptlyAPIError(
                f"Published repository does not reference requested snapshot after "
                f"publish operation: prefix={prefix or '.'}, "
                f"distribution={distribution}, snapshot={snapshot_name}, "
                f"publish={publish}"
            )

        return publish

    def publish_exists(
        self,
        *,
        prefix: str | None,
        distribution: str,
        storage: str | None = None,
    ) -> bool:
        return self._find_publish(
            prefix=prefix,
            distribution=distribution,
            storage=storage,
        ) is not None

    def publish_snapshot(
        self,
        *,
        snapshot_name: str,
        prefix: str | None = ".",
        storage: str | None = None,
        distribution: str | None = None,
        component: str = "main",
        architectures: list[str] | None = None,
        label: str | None = None,
        origin: str | None = None,
        force_overwrite: bool = False,
        skip_cleanup: bool = False,
        acquire_by_hash: bool | None = None,
        multi_dist: bool | None = None,
        not_automatic: str | None = None,
        but_automatic_upgrades: str | None = None,
        signing: dict[str, Any] | None = None,
        fail_if_exists: bool = True,
        poll_interval: int = 5,
        max_wait_seconds: int = 3600,
        progress_callback: TaskProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        publish کردن snapshot برای اولین بار.

        معادل تقریبی CLI:

            aptly publish snapshot \
              -component=<component> \
              -distribution=<distribution> \
              <snapshot_name> <prefix>

        اگر publish با prefix + distribution از قبل وجود داشته باشد:
        - fail_if_exists=True  -> خطا
        - fail_if_exists=False -> publish موجود را برمی‌گرداند
        """

        if distribution and self.publish_exists(
            prefix=prefix,
            distribution=distribution,
            storage=storage,
        ):
            existing = self._find_publish(
                prefix=prefix,
                distribution=distribution,
                storage=storage,
            )

            if fail_if_exists:
                raise AptlyAPIError(
                    f"Published repository already exists: "
                    f"prefix={prefix or '.'}, distribution={distribution}"
                )

            return {
                "mode": "exists",
                "created": False,
                "prefix": prefix or ".",
                "distribution": distribution,
                "publish": existing,
            }

        api_prefix = self._build_publish_api_prefix(
            storage=storage,
            prefix=prefix,
        )
        encoded_prefix = self._encode_publish_prefix(api_prefix)

        body: dict[str, Any] = {
            "SourceKind": "snapshot",
            "Sources": [
                {
                    "Name": snapshot_name,
                    "Component": component,
                }
            ],
            "ForceOverwrite": force_overwrite,
        }

        if distribution:
            body["Distribution"] = distribution

        if architectures:
            body["Architectures"] = architectures

        if label is not None:
            body["Label"] = label

        if origin is not None:
            body["Origin"] = origin

        if skip_cleanup:
            body["SkipCleanup"] = True

        if acquire_by_hash is not None:
            body["AcquireByHash"] = acquire_by_hash

        if multi_dist is not None:
            body["MultiDist"] = multi_dist

        if not_automatic is not None:
            body["NotAutomatic"] = not_automatic

        if but_automatic_upgrades is not None:
            body["ButAutomaticUpgrades"] = but_automatic_upgrades

        if signing is not None:
            body["Signing"] = signing

        try:
            data = self.request(
                "POST",
                f"/api/publish/{encoded_prefix}",
                params={"_async": "1"},
                json=body,
            )
        except AptlyAPIError as exc:
            # race condition یا publish قبلی
            if "already" in str(exc).lower() or "400" in str(exc):
                if distribution and not fail_if_exists:
                    existing = self._find_publish(
                        prefix=prefix,
                        distribution=distribution,
                        storage=storage,
                    )

                    if existing:
                        return {
                            "mode": "exists",
                            "created": False,
                            "prefix": prefix or ".",
                            "distribution": distribution,
                            "publish": existing,
                        }

            raise

        task_result = self._wait_task_response_if_present(
            data,
            poll_interval=poll_interval,
            max_wait_seconds=max_wait_seconds,
            progress_callback=progress_callback,
        )
        verified_publish = self._get_verified_snapshot_publish(
            prefix=prefix,
            distribution=distribution,
            storage=storage,
            snapshot_name=snapshot_name,
        )

        return {
            "mode": "publish",
            "created": True,
            "prefix": prefix or ".",
            "storage": storage,
            "distribution": distribution,
            "snapshot_name": snapshot_name,
            "task_result": task_result,
            "publish": verified_publish,
        }

    def switch_published_snapshot(
        self,
        *,
        snapshot_name: str,
        prefix: str | None = ".",
        storage: str | None = None,
        distribution: str,
        component: str = "main",
        force_overwrite: bool = False,
        acquire_by_hash: bool | None = None,
        multi_dist: bool | None = None,
        signing: dict[str, Any] | None = None,
        fail_if_missing: bool = True,
        poll_interval: int = 5,
        max_wait_seconds: int = 3600,
        progress_callback: TaskProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        تغییر publish موجود به snapshot جدید.

        معادل تقریبی CLI:

            aptly publish switch <distribution> <prefix> <snapshot_name>

        این متد برای زمانی است که publish قبلاً وجود دارد.
        """

        existing = self._find_publish(
            prefix=prefix,
            distribution=distribution,
            storage=storage,
        )

        if existing is None:
            if fail_if_missing:
                raise AptlyAPIError(
                    f"Published repository does not exist: "
                    f"prefix={prefix or '.'}, distribution={distribution}"
                )

            return {
                "mode": "missing",
                "updated": False,
                "prefix": prefix or ".",
                "distribution": distribution,
                "publish": None,
            }

        if existing.get("SourceKind") != "snapshot":
            raise AptlyAPIError(
                f"Published repository is not snapshot-based: "
                f"prefix={prefix or '.'}, distribution={distribution}, "
                f"source_kind={existing.get('SourceKind')}"
            )

        api_prefix = self._build_publish_api_prefix(
            storage=storage,
            prefix=prefix,
        )
        encoded_prefix = self._encode_publish_prefix(api_prefix)
        encoded_distribution = quote(distribution, safe="")

        body: dict[str, Any] = {
            "Snapshots": [
                {
                    "Name": snapshot_name,
                    "Component": component,
                }
            ],
            "ForceOverwrite": force_overwrite,
        }

        if acquire_by_hash is not None:
            body["AcquireByHash"] = acquire_by_hash

        if multi_dist is not None:
            body["MultiDist"] = multi_dist

        if signing is not None:
            body["Signing"] = signing

        data = self.request(
            "PUT",
            f"/api/publish/{encoded_prefix}/{encoded_distribution}",
            params={"_async": "1"},
            json=body,
        )

        task_result = self._wait_task_response_if_present(
            data,
            poll_interval=poll_interval,
            max_wait_seconds=max_wait_seconds,
            progress_callback=progress_callback,
        )
        verified_publish = self._get_verified_snapshot_publish(
            prefix=prefix,
            distribution=distribution,
            storage=storage,
            snapshot_name=snapshot_name,
        )

        return {
            "mode": "switch",
            "updated": True,
            "prefix": prefix or ".",
            "storage": storage,
            "distribution": distribution,
            "snapshot_name": snapshot_name,
            "task_result": task_result,
            "publish": verified_publish,
        }

    def publish_or_switch_snapshot(
        self,
        *,
        snapshot_name: str,
        prefix: str | None = ".",
        storage: str | None = None,
        distribution: str,
        component: str = "main",
        architectures: list[str] | None = None,
        label: str | None = None,
        origin: str | None = None,
        force_overwrite: bool = False,
        skip_cleanup: bool = False,
        acquire_by_hash: bool | None = None,
        multi_dist: bool | None = None,
        not_automatic: str | None = None,
        but_automatic_upgrades: str | None = None,
        signing: dict[str, Any] | None = None,
        poll_interval: int = 5,
        max_wait_seconds: int = 3600,
        progress_callback: TaskProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        اگر publish وجود نداشت، publish می‌کند.
        اگر publish وجود داشت، آن را به snapshot جدید switch می‌کند.

        این متد برای job اصلی پروژه مناسب‌تر است.
        """

        existing = self._find_publish(
            prefix=prefix,
            distribution=distribution,
            storage=storage,
        )

        if existing is None:
            return self.publish_snapshot(
                snapshot_name=snapshot_name,
                prefix=prefix,
                storage=storage,
                distribution=distribution,
                component=component,
                architectures=architectures,
                label=label,
                origin=origin,
                force_overwrite=force_overwrite,
                skip_cleanup=skip_cleanup,
                acquire_by_hash=acquire_by_hash,
                multi_dist=multi_dist,
                not_automatic=not_automatic,
                but_automatic_upgrades=but_automatic_upgrades,
                signing=signing,
                fail_if_exists=True,
                poll_interval=poll_interval,
                max_wait_seconds=max_wait_seconds,
                progress_callback=progress_callback,
            )

        return self.switch_published_snapshot(
            snapshot_name=snapshot_name,
            prefix=prefix,
            storage=storage,
            distribution=distribution,
            component=component,
            force_overwrite=force_overwrite,
            acquire_by_hash=acquire_by_hash,
            multi_dist=multi_dist,
            signing=signing,
            fail_if_missing=True,
            poll_interval=poll_interval,
            max_wait_seconds=max_wait_seconds,
            progress_callback=progress_callback,
        )

    def drop_publish(
        self,
        *,
        prefix: str | None = ".",
        storage: str | None = None,
        distribution: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        حذف published repository.

        معادل تقریبی CLI:

            aptly publish drop <distribution> <prefix>
        """

        api_prefix = self._build_publish_api_prefix(
            storage=storage,
            prefix=prefix,
        )
        encoded_prefix = self._encode_publish_prefix(api_prefix)
        encoded_distribution = quote(distribution, safe="")

        params: dict[str, str] = {}
        if force:
            params["force"] = "1"

        data = self.request(
            "DELETE",
            f"/api/publish/{encoded_prefix}/{encoded_distribution}",
            params=params,
        )

        return {
            "prefix": prefix or ".",
            "storage": storage,
            "distribution": distribution,
            "dropped": True,
            "result": data,
        }
