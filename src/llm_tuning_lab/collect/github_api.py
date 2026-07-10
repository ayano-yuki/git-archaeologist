from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class GitHubClient:
    base_url: str = "https://api.github.com"
    token: str | None = None
    user_agent: str = "llm-tuning-lab"

    @classmethod
    def from_env(cls) -> "GitHubClient":
        return cls(token=os.environ.get("GITHUB_TOKEN"))

    def build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        clean_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url.rstrip('/')}{clean_path}"
        clean_params = {key: value for key, value in (params or {}).items() if value not in (None, "")}
        if clean_params:
            return f"{url}?{urlencode(clean_params, doseq=True)}"
        return url

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        request = Request(self.build_url(path, params), headers=self._headers())
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API request failed: {exc.code} {detail}") from exc

    def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        max_pages: int,
        per_page: int,
    ) -> list[Any]:
        results: list[Any] = []
        for page in range(1, max_pages + 1):
            page_params = dict(params or {})
            page_params.update({"page": page, "per_page": per_page})
            payload = self.get_json(path, page_params)
            if not isinstance(payload, list):
                raise TypeError(f"Expected list response from {path}, got {type(payload).__name__}")
            if not payload:
                break
            results.extend(payload)
        return results

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self.user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
