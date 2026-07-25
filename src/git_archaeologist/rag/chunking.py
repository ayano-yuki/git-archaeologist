"""Citation-preserving chunk schema and split rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Any, Mapping


DEFAULT_MAX_CHARS = 800


class ChunkKind(StrEnum):
    """Meaningful text units used by the RAG index."""

    PULL_REQUEST_BODY = "pull_request_body"
    REVIEW_COMMENT = "review_comment"
    ISSUE_COMMENT = "issue_comment"
    DIFF_HUNK = "diff_hunk"
    COMMIT_MESSAGE = "commit_message"


@dataclass(frozen=True)
class EvidenceChunk:
    """Search chunk that can be traced back to a parent event and source URL."""

    chunk_id: str
    chunk_kind: ChunkKind
    parent_event_id: str
    source_url: str
    text: str
    sequence: int
    occurred_at: str | None = None
    previous_context: str | None = None
    next_context: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.chunk_id:
            raise ValueError("chunk_id must be non-empty")
        if not self.parent_event_id:
            raise ValueError("parent_event_id must be non-empty")
        if not self.source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be an http or https URL")
        if not self.text.strip():
            raise ValueError("text must be non-empty")
        if self.sequence < 0:
            raise ValueError("sequence must be zero or positive")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["chunk_kind"] = self.chunk_kind.value
        return {key: value for key, value in payload.items() if value is not None}


def chunk_text_artifact(
    *,
    chunk_kind: ChunkKind,
    parent_event_id: str,
    source_url: str,
    text: str,
    occurred_at: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[EvidenceChunk, ...]:
    """Split comment-like text on paragraph boundaries with context pointers."""

    _validate_max_chars(max_chars)
    units = _paragraph_units(text)
    if not units:
        return ()
    groups = _pack_units(units, max_chars=max_chars)
    return _chunks_from_groups(
        chunk_kind=chunk_kind,
        parent_event_id=parent_event_id,
        source_url=source_url,
        groups=groups,
        occurred_at=occurred_at,
        metadata=metadata or {},
    )


def chunk_commit_message(
    *,
    parent_event_id: str,
    source_url: str,
    subject: str,
    body: str = "",
    occurred_at: str | None = None,
) -> tuple[EvidenceChunk, ...]:
    """Create a commit message chunk without splitting short messages."""

    message = "\n\n".join(part for part in (subject.strip(), body.strip()) if part)
    return chunk_text_artifact(
        chunk_kind=ChunkKind.COMMIT_MESSAGE,
        parent_event_id=parent_event_id,
        source_url=source_url,
        text=message,
        occurred_at=occurred_at,
        metadata={"subject": subject},
    )


def chunk_diff_hunk(
    *,
    parent_event_id: str,
    source_url: str,
    hunk: str,
    file_path: str,
    occurred_at: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[EvidenceChunk, ...]:
    """Split a diff hunk on hunk headers and line groups."""

    _validate_max_chars(max_chars)
    groups: list[str] = []
    for unit in _diff_units(hunk):
        if len(unit) > max_chars:
            groups.extend(_split_long_unit(unit, max_chars=max_chars))
        else:
            groups.append(unit)
    return _chunks_from_groups(
        chunk_kind=ChunkKind.DIFF_HUNK,
        parent_event_id=parent_event_id,
        source_url=source_url,
        groups=tuple(groups),
        occurred_at=occurred_at,
        metadata={"file_path": file_path},
    )


def _chunks_from_groups(
    *,
    chunk_kind: ChunkKind,
    parent_event_id: str,
    source_url: str,
    groups: tuple[str, ...],
    occurred_at: str | None,
    metadata: Mapping[str, Any],
) -> tuple[EvidenceChunk, ...]:
    chunks: list[EvidenceChunk] = []
    for index, group in enumerate(groups):
        previous_context = groups[index - 1][-160:] if index > 0 else None
        next_context = groups[index + 1][:160] if index + 1 < len(groups) else None
        chunks.append(
            EvidenceChunk(
                chunk_id=_chunk_id(parent_event_id, chunk_kind, index, group),
                chunk_kind=chunk_kind,
                parent_event_id=parent_event_id,
                source_url=source_url,
                text=group,
                sequence=index,
                occurred_at=occurred_at,
                previous_context=previous_context,
                next_context=next_context,
                metadata=dict(metadata),
            )
        )
    return tuple(chunks)


def _paragraph_units(text: str) -> tuple[str, ...]:
    units = [part.strip() for part in text.split("\n\n") if part.strip()]
    if units:
        return tuple(units)
    stripped = text.strip()
    return (stripped,) if stripped else ()


def _diff_units(hunk: str) -> tuple[str, ...]:
    units: list[str] = []
    current: list[str] = []
    for line in hunk.splitlines():
        if line.startswith("@@") and current:
            units.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        units.append("\n".join(current))
    return tuple(unit for unit in units if unit.strip())


def _pack_units(units: tuple[str, ...], *, max_chars: int) -> tuple[str, ...]:
    groups: list[str] = []
    current = ""
    for unit in units:
        if len(unit) > max_chars:
            if current:
                groups.append(current)
                current = ""
            groups.extend(_split_long_unit(unit, max_chars=max_chars))
            continue
        candidate = unit if not current else f"{current}\n\n{unit}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            groups.append(current)
            current = unit
    if current:
        groups.append(current)
    return tuple(groups)


def _split_long_unit(unit: str, *, max_chars: int) -> tuple[str, ...]:
    lines = unit.splitlines()
    groups: list[str] = []
    current = ""
    for line in lines:
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                groups.append(current)
            current = line
    if current:
        groups.append(current)
    return tuple(groups)


def _chunk_id(
    parent_event_id: str,
    chunk_kind: ChunkKind,
    sequence: int,
    text: str,
) -> str:
    digest = sha256(
        f"{parent_event_id}\0{chunk_kind.value}\0{sequence}\0{text}".encode("utf-8")
    ).hexdigest()[:16]
    return f"chunk-{chunk_kind.value}-{digest}"


def _validate_max_chars(max_chars: int) -> None:
    if max_chars < 80:
        raise ValueError("max_chars must be at least 80")
