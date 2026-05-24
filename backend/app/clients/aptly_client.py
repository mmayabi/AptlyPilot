from __future__ import annotations

from typing import Any

import requests


class AptlyAPIError(Exception):
    pass


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