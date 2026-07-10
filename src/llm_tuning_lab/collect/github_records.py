from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def wrap_github_record(repo: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "github",
        "repo": repo,
        "kind": kind,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "github_id": payload.get("id") or payload.get("node_id") or payload.get("sha"),
        "number": payload.get("number"),
        "html_url": payload.get("html_url"),
        "api_url": payload.get("url"),
        "data": payload,
    }


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
            count += 1
    return count


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
