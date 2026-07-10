import json
from pathlib import Path
from typing import Any

from llm_tuning_lab.collect.github import collect_repo


class FakeGitHubClient:
    def paginate(
        self,
        path: str,
        params: dict[str, Any],
        *,
        max_pages: int,
        per_page: int,
    ) -> list[dict[str, Any]]:
        if path.endswith("/pulls"):
            return [{"id": 1, "number": 10, "html_url": "https://example.test/pull/10"}]
        if path.endswith("/issues"):
            return [{"id": 2, "number": 20, "html_url": "https://example.test/issues/20"}]
        if path.endswith("/commits"):
            return [{"sha": "abc", "html_url": "https://example.test/commit/abc"}]
        return []


def test_collect_repo_writes_manifest_and_jsonl(tmp_path: Path) -> None:
    config = {
        "repo": "react/react",
        "output_dir": str(tmp_path),
        "max_pages": 1,
        "per_page": 10,
    }

    manifest = collect_repo(config, FakeGitHubClient())

    assert manifest["counts"] == {"pulls": 1, "issues": 1, "commits": 1}
    assert (tmp_path / "pulls.jsonl").exists()
    written_manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert written_manifest["repo"] == "react/react"
