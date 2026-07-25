"""Deterministic symbol index schema and lookup helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any


SYMBOL_INDEX_SCHEMA_VERSION = 1


class SymbolMatchKind(StrEnum):
    """Why a symbol candidate was returned."""

    FILE_MATCH = "file_match"
    SYMBOL_MATCH = "symbol_match"
    RENAMED_FILE_MATCH = "renamed_file_match"
    UNSUPPORTED_LANGUAGE = "unsupported_language"


@dataclass(frozen=True)
class SymbolRange:
    """Line range for a symbol in one file revision."""

    start_line: int
    end_line: int

    def validate(self) -> None:
        if self.start_line < 1:
            raise ValueError("start_line must be positive")
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")

    def to_dict(self) -> dict[str, int]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class SymbolRecord:
    """One indexed symbol at one commit."""

    qualified_name: str
    file_path: str
    language: str
    commit_sha: str
    content_hash: str
    symbol_range: SymbolRange
    symbol_id: str | None = None
    previous_file_path: str | None = None
    unsupported_reason: str | None = None
    schema_version: int = SYMBOL_INDEX_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()
        if self.symbol_id is None:
            object.__setattr__(self, "symbol_id", stable_symbol_id(self))

    def validate(self) -> None:
        if self.schema_version != SYMBOL_INDEX_SCHEMA_VERSION:
            raise ValueError("unsupported symbol index schema_version")
        for field_name in ("qualified_name", "file_path", "language", "commit_sha", "content_hash"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be non-empty")
        self.symbol_range.validate()

    def to_dict(self) -> dict[str, object]:
        self.validate()
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "symbol_id": self.symbol_id or stable_symbol_id(self),
            "qualified_name": self.qualified_name,
            "file_path": self.file_path,
            "language": self.language,
            "commit_sha": self.commit_sha,
            "content_hash": self.content_hash,
            "range": self.symbol_range.to_dict(),
        }
        if self.previous_file_path:
            payload["previous_file_path"] = self.previous_file_path
        if self.unsupported_reason:
            payload["unsupported_reason"] = self.unsupported_reason
        return payload


@dataclass(frozen=True)
class SymbolCandidate:
    """Lookup result with an explicit match reason."""

    record: SymbolRecord
    match_kind: SymbolMatchKind
    score: float
    ambiguity_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "record": self.record.to_dict(),
            "match_kind": self.match_kind.value,
            "score": self.score,
            "ambiguity_reason": self.ambiguity_reason,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class SymbolIndex:
    """In-memory symbol index contract used before persistent storage exists."""

    records: tuple[SymbolRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))

    def find_by_file(self, file_path: str, *, commit_sha: str | None = None) -> tuple[SymbolCandidate, ...]:
        candidates: list[SymbolCandidate] = []
        for record in self._at_commit(commit_sha):
            if record.file_path == file_path:
                candidates.append(SymbolCandidate(record, SymbolMatchKind.FILE_MATCH, 1.0))
            elif record.previous_file_path == file_path:
                candidates.append(
                    SymbolCandidate(
                        record,
                        SymbolMatchKind.RENAMED_FILE_MATCH,
                        0.85,
                        ambiguity_reason="file matched previous_file_path from rename metadata",
                    )
                )
        return tuple(candidates)

    def find_by_symbol(self, symbol_name: str, *, commit_sha: str | None = None) -> tuple[SymbolCandidate, ...]:
        normalized = symbol_name.lower()
        candidates: list[SymbolCandidate] = []
        for record in self._at_commit(commit_sha):
            name = record.qualified_name.lower()
            if name == normalized or name.endswith(f".{normalized}"):
                candidates.append(SymbolCandidate(record, SymbolMatchKind.SYMBOL_MATCH, 1.0))
            elif normalized in name:
                candidates.append(
                    SymbolCandidate(
                        record,
                        SymbolMatchKind.SYMBOL_MATCH,
                        0.65,
                        ambiguity_reason="partial symbol name match",
                    )
                )
        return tuple(sorted(candidates, key=lambda candidate: candidate.score, reverse=True))

    def unsupported_for_file(self, file_path: str, reason: str) -> SymbolCandidate:
        record = SymbolRecord(
            qualified_name=file_path,
            file_path=file_path,
            language="unsupported",
            commit_sha="0000000",
            content_hash="sha256:unsupported",
            symbol_range=SymbolRange(start_line=1, end_line=1),
            unsupported_reason=reason,
        )
        return SymbolCandidate(
            record=record,
            match_kind=SymbolMatchKind.UNSUPPORTED_LANGUAGE,
            score=0.0,
            ambiguity_reason=reason,
        )

    def _at_commit(self, commit_sha: str | None) -> tuple[SymbolRecord, ...]:
        if commit_sha is None:
            return self.records
        return tuple(record for record in self.records if record.commit_sha == commit_sha)


def stable_symbol_id(record: SymbolRecord) -> str:
    """Return a stable symbol ID tied to file, name, commit, and content hash."""

    digest = sha256(
        "\0".join(
            (
                record.qualified_name,
                record.file_path,
                record.commit_sha,
                record.content_hash,
                str(record.symbol_range.start_line),
                str(record.symbol_range.end_line),
            )
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"symbol-{digest}"


def symbol_index_to_dict(index: SymbolIndex) -> dict[str, Any]:
    """Serialize the index contract."""

    return {
        "schema_version": SYMBOL_INDEX_SCHEMA_VERSION,
        "records": [record.to_dict() for record in index.records],
    }
