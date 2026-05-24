#!/usr/bin/env python3
"""
Update existing aptly mirrors via aptly REST API.

Default behavior:
  - Uses async mode: PUT /api/mirrors/:name?_async=1
  - Polls /api/tasks/:task_id until success/failure/timeout
  - Saves a JSON report

Examples:
  python3 aptly_update_mirrors.py \
    --api-url http://127.0.0.1:8080 \
    --mirrors debian-bookworm,ubuntu-jammy \
    --output report.json

  python3 aptly_update_mirrors.py \
    --api-url http://127.0.0.1:8080 \
    --all \
    --skip-existing-packages \
    --output report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests


SUCCESS_STATES = {
    "success",
    "succeeded",
    "done",
    "completed",
    "complete",
    "finished",
    "2",
}

FAILED_STATES = {
    "failed",
    "failure",
    "error",
    "errored",
    "cancelled",
    "canceled",
    "3",
}

RUNNING_STATES = {
    "running",
    "processing",
    "in_progress",
    "waiting",
    "queued",
    "pending",
    "created",
    "0",
    "1",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AptlyApiError(RuntimeError):
    pass


class AptlyClient:
    def __init__(self, api_url: str, request_timeout: int = 30) -> None:
        self.api_url = api_url.rstrip("/")
        self.request_timeout = request_timeout
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.api_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> Any:
        url = self._url(path)

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                timeout=self.request_timeout,
            )
        except requests.RequestException as exc:
            raise AptlyApiError(f"Request failed: {method} {url}: {exc}") from exc

        if response.status_code not in expected_statuses:
            body = response.text.strip()
            raise AptlyApiError(
                f"Unexpected HTTP status {response.status_code} for {method} {url}. "
                f"Response body: {body}"
            )

        if not response.text.strip():
            return None

        try:
            return response.json()
        except ValueError:
            return response.text

    def get_version(self) -> Any:
        return self._request("GET", "/api/version")

    def list_mirrors(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/api/mirrors")
        if not isinstance(data, list):
            raise AptlyApiError(f"Unexpected mirrors response: {data}")
        return data

    def get_mirror(self, name: str) -> Dict[str, Any]:
        encoded_name = quote(name, safe="")
        data = self._request("GET", f"/api/mirrors/{encoded_name}")
        if not isinstance(data, dict):
            raise AptlyApiError(f"Unexpected mirror response for {name}: {data}")
        return data

    def update_mirror_async(
        self,
        name: str,
        *,
        force_update: bool = False,
        skip_existing_packages: bool = False,
    ) -> Any:
        encoded_name = quote(name, safe="")

        body: Dict[str, Any] = {}

        # این دو گزینه در API mirror edit/update وجود دارند.
        # فقط وقتی کاربر صراحتاً فعال کند ارسال می‌شوند.
        if force_update:
            body["ForceUpdate"] = True

        if skip_existing_packages:
            body["SkipExistingPackages"] = True

        return self._request(
            "PUT",
            f"/api/mirrors/{encoded_name}",
            params={"_async": "1"},
            json_body=body,
            expected_statuses=(200, 201, 202),
        )

    def update_mirror_sync(
        self,
        name: str,
        *,
        force_update: bool = False,
        skip_existing_packages: bool = False,
    ) -> Any:
        encoded_name = quote(name, safe="")

        body: Dict[str, Any] = {}

        if force_update:
            body["ForceUpdate"] = True

        if skip_existing_packages:
            body["SkipExistingPackages"] = True

        return self._request(
            "PUT",
            f"/api/mirrors/{encoded_name}",
            json_body=body,
            expected_statuses=(200, 201, 202),
        )

    def get_task(self, task_id: str) -> Any:
        encoded_task_id = quote(str(task_id), safe="")
        return self._request("GET", f"/api/tasks/{encoded_task_id}")


def extract_task_id(response: Any) -> Optional[str]:
    """
    aptly versions may return task ID in slightly different shapes.
    This function tries common formats safely.
    """
    if response is None:
        return None

    if isinstance(response, str):
        value = response.strip()
        return value or None

    if isinstance(response, int):
        return str(response)

    if isinstance(response, dict):
        for key in (
            "ID",
            "Id",
            "id",
            "TaskID",
            "taskID",
            "task_id",
            "UUID",
            "uuid",
        ):
            if key in response and response[key] not in (None, ""):
                return str(response[key])

        # Sometimes response may be nested.
        for key in ("Task", "task"):
            nested = response.get(key)
            if isinstance(nested, dict):
                task_id = extract_task_id(nested)
                if task_id:
                    return task_id

    return None


def extract_task_state(task: Any) -> Optional[str]:
    if not isinstance(task, dict):
        return None

    for key in (
        "State",
        "state",
        "Status",
        "status",
        "TaskState",
        "taskState",
        "task_state",
    ):
        value = task.get(key)
        if value is not None:
            return str(value).strip().lower()

    return None


def extract_task_error(task: Any) -> Optional[str]:
    if not isinstance(task, dict):
        return None

    for key in (
        "Error",
        "error",
        "Err",
        "err",
        "ErrorMessage",
        "errorMessage",
        "Failure",
        "failure",
    ):
        value = task.get(key)
        if value:
            return str(value)

    return None


def extract_task_output(task: Any) -> Optional[str]:
    if not isinstance(task, dict):
        return None

    for key in (
        "Output",
        "output",
        "Stdout",
        "stdout",
        "Log",
        "log",
        "Result",
        "result",
    ):
        value = task.get(key)
        if value:
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            return str(value)

    return None


def classify_task(task: Any) -> str:
    """
    Returns one of:
      - success
      - failed
      - running
      - unknown
    """
    state = extract_task_state(task)
    error = extract_task_error(task)

    if error:
        return "failed"

    if state:
        if state in SUCCESS_STATES:
            return "success"
        if state in FAILED_STATES:
            return "failed"
        if state in RUNNING_STATES:
            return "running"

    if isinstance(task, dict):
        done = task.get("Done") or task.get("done") or task.get("Finished") or task.get("finished")
        if done is True:
            return "success"

    return "unknown"


def poll_task(
    client: AptlyClient,
    task_id: str,
    *,
    poll_interval: int,
    task_timeout: int,
) -> Dict[str, Any]:
    started = time.time()
    last_task: Any = None

    while True:
        elapsed = int(time.time() - started)

        if elapsed > task_timeout:
            return {
                "status": "timeout",
                "task_id": task_id,
                "elapsed_seconds": elapsed,
                "error": f"Task polling timeout after {task_timeout} seconds",
                "last_task_response": last_task,
            }

        try:
            task = client.get_task(task_id)
            last_task = task
        except Exception as exc:
            return {
                "status": "failed",
                "task_id": task_id,
                "elapsed_seconds": elapsed,
                "error": str(exc),
                "last_task_response": last_task,
            }

        task_status = classify_task(task)
        state = extract_task_state(task)

        if task_status == "success":
            return {
                "status": "success",
                "task_id": task_id,
                "state": state,
                "elapsed_seconds": elapsed,
                "output": extract_task_output(task),
                "raw_task_response": task,
            }

        if task_status == "failed":
            return {
                "status": "failed",
                "task_id": task_id,
                "state": state,
                "elapsed_seconds": elapsed,
                "error": extract_task_error(task) or "Task failed",
                "output": extract_task_output(task),
                "raw_task_response": task,
            }

        print(
            f"  task={task_id} state={state or 'unknown'} elapsed={elapsed}s",
            flush=True,
        )
        time.sleep(poll_interval)


def load_mirrors_from_file(path: str) -> List[str]:
    mirrors: List[str] = []

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        mirrors.append(line)

    return mirrors


def normalize_mirror_list(value: Optional[str]) -> List[str]:
    if not value:
        return []

    return [item.strip() for item in value.split(",") if item.strip()]


def update_one_mirror(
    client: AptlyClient,
    mirror_name: str,
    *,
    mode: str,
    poll_interval: int,
    task_timeout: int,
    force_update: bool,
    skip_existing_packages: bool,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "mirror": mirror_name,
        "mode": mode,
        "started_at": utc_now(),
        "finished_at": None,
        "status": "unknown",
        "error": None,
        "task_id": None,
        "raw_update_response": None,
        "task_result": None,
    }

    try:
        # اول وجود mirror را چک می‌کنیم تا خطای 404 واضح‌تر شود.
        mirror_info = client.get_mirror(mirror_name)
        result["mirror_info_before_update"] = mirror_info

        if mode == "sync":
            print(f"[SYNC] Updating mirror: {mirror_name}", flush=True)
            update_response = client.update_mirror_sync(
                mirror_name,
                force_update=force_update,
                skip_existing_packages=skip_existing_packages,
            )
            result["raw_update_response"] = update_response
            result["status"] = "success"
            return result

        print(f"[ASYNC] Updating mirror: {mirror_name}", flush=True)
        update_response = client.update_mirror_async(
            mirror_name,
            force_update=force_update,
            skip_existing_packages=skip_existing_packages,
        )
        result["raw_update_response"] = update_response

        task_id = extract_task_id(update_response)
        result["task_id"] = task_id

        if not task_id:
            result["status"] = "failed"
            result["error"] = (
                "Async update response did not contain a task id. "
                "Check raw_update_response."
            )
            return result

        task_result = poll_task(
            client,
            task_id,
            poll_interval=poll_interval,
            task_timeout=task_timeout,
        )
        result["task_result"] = task_result
        result["status"] = task_result.get("status", "unknown")
        result["error"] = task_result.get("error")

        return result

    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        return result

    finally:
        result["finished_at"] = utc_now()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update aptly mirrors via REST API"
    )

    parser.add_argument(
        "--api-url",
        required=True,
        help="aptly API URL, e.g. http://127.0.0.1:8080",
    )

    parser.add_argument(
        "--mirrors",
        help="Comma-separated mirror names, e.g. debian-bookworm,ubuntu-jammy",
    )

    parser.add_argument(
        "--mirrors-file",
        help="File containing mirror names, one per line",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Update all mirrors returned by GET /api/mirrors",
    )

    parser.add_argument(
        "--mode",
        choices=("async", "sync"),
        default="async",
        help="Update mode. Default: async",
    )

    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Seconds between task status checks. Default: 10",
    )

    parser.add_argument(
        "--task-timeout",
        type=int,
        default=6 * 60 * 60,
        help="Max seconds to wait for each task. Default: 21600 / 6h",
    )

    parser.add_argument(
        "--request-timeout",
        type=int,
        default=30,
        help="HTTP request timeout in seconds. Default: 30",
    )

    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Send ForceUpdate=true. Use with caution.",
    )

    parser.add_argument(
        "--skip-existing-packages",
        action="store_true",
        help="Send SkipExistingPackages=true",
    )

    parser.add_argument(
        "--output",
        default="aptly_mirror_update_report.json",
        help="Output JSON report path",
    )

    args = parser.parse_args()

    client = AptlyClient(
        api_url=args.api_url,
        request_timeout=args.request_timeout,
    )

    mirrors: List[str] = []

    if args.all:
        all_mirrors = client.list_mirrors()
        mirrors.extend([m["Name"] for m in all_mirrors if isinstance(m, dict) and m.get("Name")])

    mirrors.extend(normalize_mirror_list(args.mirrors))

    if args.mirrors_file:
        mirrors.extend(load_mirrors_from_file(args.mirrors_file))

    # حذف تکراری‌ها با حفظ ترتیب
    mirrors = list(dict.fromkeys(mirrors))

    if not mirrors:
        print(
            "No mirrors selected. Use --all, --mirrors, or --mirrors-file.",
            file=sys.stderr,
        )
        return 2

    report: Dict[str, Any] = {
        "api_url": args.api_url,
        "mode": args.mode,
        "started_at": utc_now(),
        "finished_at": None,
        "options": {
            "poll_interval": args.poll_interval,
            "task_timeout": args.task_timeout,
            "request_timeout": args.request_timeout,
            "force_update": args.force_update,
            "skip_existing_packages": args.skip_existing_packages,
        },
        "mirrors": mirrors,
        "results": [],
        "summary": {
            "total": len(mirrors),
            "success": 0,
            "failed": 0,
            "timeout": 0,
            "unknown": 0,
        },
    }

    try:
        version = client.get_version()
        report["aptly_version"] = version
        print(f"Connected to aptly API: {version}", flush=True)
    except Exception as exc:
        print(f"WARNING: Could not fetch aptly version: {exc}", file=sys.stderr)
        report["aptly_version_error"] = str(exc)

    for mirror_name in mirrors:
        item = update_one_mirror(
            client,
            mirror_name,
            mode=args.mode,
            poll_interval=args.poll_interval,
            task_timeout=args.task_timeout,
            force_update=args.force_update,
            skip_existing_packages=args.skip_existing_packages,
        )

        report["results"].append(item)

        status = item.get("status", "unknown")
        if status in report["summary"]:
            report["summary"][status] += 1
        else:
            report["summary"]["unknown"] += 1

        print(
            f"[RESULT] mirror={mirror_name} status={status} "
            f"task_id={item.get('task_id')} error={item.get('error')}",
            flush=True,
        )

    report["finished_at"] = utc_now()

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nSummary:")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"\nReport saved to: {output_path}")

    if report["summary"]["failed"] > 0 or report["summary"]["timeout"] > 0:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())