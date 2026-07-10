from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

KIND_FILES = (
    "pulls.jsonl",
    "issues.jsonl",
    "commits.jsonl",
    "issue_comments.jsonl",
    "pull_review_comments.jsonl",
    "pull_reviews.jsonl",
)

SYSTEM_PROMPT = (
    "You are Git Archaeologist. Use repository evidence first, separate facts from "
    "inference, and avoid claiming that a single record proves more than it shows."
)


def load_github_records(input_path: Path) -> list[dict[str, Any]]:
    if input_path.is_file():
        return list(_read_jsonl(input_path))
    if not input_path.is_dir():
        raise FileNotFoundError(f"input path does not exist: {input_path}")

    records: list[dict[str, Any]] = []
    for file_name in KIND_FILES:
        path = input_path / file_name
        if path.exists():
            records.extend(_read_jsonl(path))
    return records


def build_sft_records(records: Iterable[dict[str, Any]], max_records: int | None = None) -> list[dict[str, Any]]:
    if max_records is not None and max_records <= 0:
        return []

    examples: list[dict[str, Any]] = []
    for record in records:
        example = github_record_to_messages(record)
        if example is not None:
            examples.append(example)
        if max_records is not None and len(examples) >= max_records:
            break
    return examples


def github_record_to_messages(record: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(record.get("kind") or "record")
    repo = str(record.get("repo") or "unknown/repo")
    data = record.get("data")
    if not isinstance(data, dict):
        return None

    identity = _record_identity(record, data)
    summary = _summarize_payload(kind, data)
    if not summary:
        return None

    user_content = (
        f"Repository: {repo}\n"
        f"Evidence kind: {kind}\n"
        f"Evidence id: {identity}\n"
        f"Evidence summary:\n{summary}\n\n"
        "Explain how this evidence should be used when reconstructing repository history."
    )
    assistant_content = (
        f"Facts: This is a {kind} record from {repo}. {summary}\n\n"
        "Inference: Use this record as one piece of supporting evidence, not as a complete "
        "answer by itself. Compare it with related commits, pull requests, issues, reviews, "
        "and CI logs before reconstructing the reason behind a code change.\n\n"
        "Uncertainty: The record may omit context such as offline discussion, linked design "
        "documents, or later reversions, so conclusions should be phrased cautiously."
    )

    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]
    }


def split_train_validation(
    records: list[dict[str, Any]],
    validation_ratio: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not records:
        raise ValueError("no SFT records were generated from input evidence")
    if len(records) == 1:
        return records, []

    ratio = min(max(validation_ratio, 0.0), 0.5)
    validation_count = max(1, round(len(records) * ratio))
    validation_count = min(validation_count, len(records) - 1)
    split_at = len(records) - validation_count
    return records[:split_at], records[split_at:]


def write_sft_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
            count += 1
    return count


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            loaded = json.loads(stripped)
            if not isinstance(loaded, dict):
                raise ValueError(f"{path}:{line_number}: JSONL record must be an object")
            yield loaded


def _record_identity(record: dict[str, Any], data: dict[str, Any]) -> str:
    number = record.get("number") or data.get("number")
    if number is not None:
        return f"#{number}"
    return str(record.get("github_id") or data.get("sha") or data.get("id") or "unknown")


def _summarize_payload(kind: str, data: dict[str, Any]) -> str:
    if kind == "commit":
        commit = data.get("commit") if isinstance(data.get("commit"), dict) else {}
        message = _clean_text(commit.get("message") or data.get("sha") or "")
        return _line("Commit message", message)

    title = _clean_text(data.get("title") or "")
    body = _clean_text(data.get("body") or "")
    state = _clean_text(data.get("state") or "")
    author = _author_login(data)

    parts = [
        _line("Title", title),
        _line("State", state),
        _line("Author", author),
        _line("Body excerpt", body),
    ]
    return "\n".join(part for part in parts if part)


def _author_login(data: dict[str, Any]) -> str:
    user = data.get("user")
    if isinstance(user, dict):
        return _clean_text(user.get("login") or "")
    return ""


def _line(label: str, value: str) -> str:
    if not value:
        return ""
    return f"- {label}: {value}"


def _clean_text(value: Any, limit: int = 600) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."
