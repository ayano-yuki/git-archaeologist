from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

KIND_FILES = (
    "pulls.jsonl",
    "pull_details.jsonl",
    "pull_commits.jsonl",
    "pull_files.jsonl",
    "issues.jsonl",
    "commits.jsonl",
    "commit_details.jsonl",
    "check_runs.jsonl",
    "issue_comments.jsonl",
    "pull_review_comments.jsonl",
    "pull_reviews.jsonl",
)

PR_PATTERN = re.compile(r"(?:pull request|PR)\s*#?(\d+)", re.IGNORECASE)
SQUASH_PR_PATTERN = re.compile(r"\(#(\d+)\)")
URL_NUMBER_PATTERN = re.compile(r"/(issues|pulls)/(\d+)(?:$|[/?#])")


def load_github_records(input_path: Path) -> list[dict[str, Any]]:
    if input_path.is_file():
        return list(read_jsonl(input_path))
    if not input_path.is_dir():
        raise FileNotFoundError(f"input path does not exist: {input_path}")

    records: list[dict[str, Any]] = []
    for file_name in KIND_FILES:
        path = input_path / file_name
        if path.exists():
            records.extend(read_jsonl(path))
    return records


def build_evidence_bundles(
    records: Iterable[dict[str, Any]],
    *,
    min_evidence_per_bundle: int = 3,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        evidence = record_to_evidence(record)
        if evidence is None:
            continue
        grouped[evidence["thread_key"]].append(evidence)

    bundles: list[dict[str, Any]] = []
    for thread_key, evidence_items in sorted(grouped.items()):
        evidence_items = sorted(evidence_items, key=_evidence_sort_key)
        evidence_items.extend(_derived_revert_evidence(evidence_items))
        if len(evidence_items) < min_evidence_per_bundle:
            continue
        repo = str(evidence_items[0]["repo"])
        bundles.append(_build_bundle(repo, thread_key, evidence_items))
    return bundles


def record_to_evidence(record: dict[str, Any]) -> dict[str, Any] | None:
    data = record.get("data")
    if not isinstance(data, dict):
        return None

    kind = str(record.get("kind") or "record")
    repo = str(record.get("repo") or "unknown/repo")
    identity = _record_identity(record, data)
    thread_key = _thread_key(kind, record, data)
    if not thread_key:
        return None

    summary = _summarize_payload(kind, data)
    if not summary:
        return None

    evidence_id = _stable_id(repo, kind, identity, summary)
    return {
        "evidence_id": evidence_id,
        "repo": repo,
        "kind": kind,
        "thread_key": thread_key,
        "source_id": identity,
        "url": record.get("html_url") or data.get("html_url") or data.get("url"),
        "created_at": data.get("created_at") or _commit_date(data),
        "updated_at": data.get("updated_at"),
        "title": _clean_text(data.get("title") or ""),
        "summary": summary,
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


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            loaded = json.loads(stripped)
            if not isinstance(loaded, dict):
                raise ValueError(f"{path}:{line_number}: JSONL record must be an object")
            yield loaded


def _build_bundle(repo: str, thread_key: str, evidence_items: list[dict[str, Any]]) -> dict[str, Any]:
    dates = [item.get("created_at") for item in evidence_items if item.get("created_at")]
    bundle_id = _stable_id(repo, thread_key, *(item["evidence_id"] for item in evidence_items))
    return {
        "bundle_id": bundle_id,
        "repo": repo,
        "thread_key": thread_key,
        "task_type": "decision_rationale",
        "question": f"Reconstruct the design rationale and uncertainty for {repo} {thread_key}.",
        "evidence": evidence_items,
        "created_at_range": {
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
        },
        "source_record_ids": [item["source_id"] for item in evidence_items],
    }


def _thread_key(kind: str, record: dict[str, Any], data: dict[str, Any]) -> str | None:
    pull_number = data.get("_parent_pull_number") or record.get("pull_number")
    if pull_number is not None:
        return f"pull:{pull_number}"

    if kind.startswith("pull"):
        number = record.get("number") or data.get("number")
        if number is not None:
            return f"pull:{number}"
        return _number_from_url(data.get("pull_request_url"))

    if kind in {"issue", "issue_comment"}:
        number = record.get("number") or data.get("number")
        if number is not None:
            return f"issue:{number}"
        return _number_from_url(data.get("issue_url"))

    if kind in {"commit", "commit_detail", "check_run"}:
        message = _commit_message(data)
        pr_number = _pr_number_from_text(message)
        if pr_number:
            return f"pull:{pr_number}"
        sha = record.get("github_id") or data.get("sha") or data.get("head_sha")
        return f"commit:{sha}" if sha else None

    return None


def _summarize_payload(kind: str, data: dict[str, Any]) -> str:
    if kind in {"commit", "commit_detail"}:
        return _line("Commit", _commit_message(data), 800)
    if kind == "check_run":
        return _join_lines(
            _line("CI name", data.get("name")),
            _line("Conclusion", data.get("conclusion") or data.get("status")),
        )
    if kind == "pull_file":
        return _join_lines(
            _line("File", data.get("filename")),
            _line("Status", data.get("status")),
            _line("Patch excerpt", data.get("patch"), 800),
        )
    if kind == "pull_commit":
        return _line("Pull commit", _commit_message(data), 800)
    return _join_lines(
        _line("Title", data.get("title")),
        _line("State", data.get("state")),
        _line("Author", _author_login(data)),
        _line("Body excerpt", data.get("body"), 800),
    )


def _derived_revert_evidence(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    derived: list[dict[str, Any]] = []
    for item in evidence_items:
        if item["kind"] not in {"commit", "commit_detail", "pull_commit"}:
            continue
        summary = str(item.get("summary") or "")
        if "revert" not in summary.lower():
            continue
        evidence_id = _stable_id(item["evidence_id"], "revert_relation")
        derived.append(
            {
                "evidence_id": evidence_id,
                "repo": item["repo"],
                "kind": "revert_relation",
                "thread_key": item["thread_key"],
                "source_id": item["source_id"],
                "url": item.get("url"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "title": "Possible revert relationship",
                "summary": f"Derived signal: {summary}",
            }
        )
    return derived


def _record_identity(record: dict[str, Any], data: dict[str, Any]) -> str:
    for key in ("number", "github_id"):
        if record.get(key) is not None:
            return str(record[key])
    return str(data.get("sha") or data.get("id") or data.get("node_id") or "unknown")


def _commit_message(data: dict[str, Any]) -> str:
    commit = data.get("commit") if isinstance(data.get("commit"), dict) else {}
    return _clean_text(commit.get("message") or data.get("message") or data.get("sha") or "")


def _commit_date(data: dict[str, Any]) -> str | None:
    commit = data.get("commit") if isinstance(data.get("commit"), dict) else {}
    author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
    date = author.get("date")
    return str(date) if date else None


def _number_from_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = URL_NUMBER_PATTERN.search(value)
    if not match:
        return None
    prefix = "issue" if match.group(1) == "issues" else "pull"
    return f"{prefix}:{match.group(2)}"


def _pr_number_from_text(value: str) -> str | None:
    match = PR_PATTERN.search(value) or SQUASH_PR_PATTERN.search(value)
    return match.group(1) if match else None


def _author_login(data: dict[str, Any]) -> str:
    user = data.get("user") or data.get("author")
    if isinstance(user, dict):
        return _clean_text(user.get("login") or "")
    return ""


def _line(label: str, value: Any, limit: int = 400) -> str:
    cleaned = _clean_text(value, limit)
    return f"- {label}: {cleaned}" if cleaned else ""


def _join_lines(*parts: str) -> str:
    return "\n".join(part for part in parts if part)


def _clean_text(value: Any, limit: int = 600) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _stable_id(*parts: object) -> str:
    raw = "\n".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _evidence_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (str(item.get("created_at") or ""), str(item.get("kind") or ""), item["evidence_id"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Git Archaeologist evidence bundles.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-evidence-per-bundle", type=int, default=3)
    args = parser.parse_args()

    records = load_github_records(args.input)
    bundles = build_evidence_bundles(
        records,
        min_evidence_per_bundle=args.min_evidence_per_bundle,
    )
    count = write_jsonl(args.output, bundles)
    print(f"raw_records: {len(records)}")
    print(f"bundles: {count} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
