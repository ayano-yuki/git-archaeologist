"""Deterministic target resolution for code snippets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from git_archaeologist.symbol_index import SymbolCandidate, SymbolIndex


class SnippetMatchKind(StrEnum):
    """How a code snippet candidate was found."""

    EXACT = "exact"
    NORMALIZED = "normalized"
    LEXICAL = "lexical"
    SYMBOL = "symbol"


class ResolutionStatus(StrEnum):
    """Final state of a deterministic snippet resolution attempt."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class CodeDocument:
    """Searchable code content for one indexed file revision."""

    document_id: str
    file_path: str
    content: str
    commit_sha: str | None = None

    def validate(self) -> None:
        for field_name in ("document_id", "file_path", "content"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be non-empty")


@dataclass(frozen=True)
class SnippetCandidate:
    """One possible code target with the reason it matched."""

    document_id: str
    file_path: str
    match_kind: SnippetMatchKind
    score: float
    reason: str
    symbol_id: str | None = None
    qualified_name: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "document_id": self.document_id,
            "file_path": self.file_path,
            "match_kind": self.match_kind.value,
            "score": self.score,
            "reason": self.reason,
            "symbol_id": self.symbol_id,
            "qualified_name": self.qualified_name,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class SnippetResolution:
    """Resolution result that explicitly gates answer generation."""

    status: ResolutionStatus
    candidates: tuple[SnippetCandidate, ...]
    selected_candidate: SnippetCandidate | None = None
    ambiguity_reason: str | None = None
    unresolved_reason: str | None = None

    @property
    def should_generate_answer(self) -> bool:
        return self.status is ResolutionStatus.RESOLVED and self.selected_candidate is not None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "status": self.status.value,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "selected_candidate": self.selected_candidate.to_dict() if self.selected_candidate else None,
            "ambiguity_reason": self.ambiguity_reason,
            "unresolved_reason": self.unresolved_reason,
            "should_generate_answer": self.should_generate_answer,
        }
        return {key: value for key, value in payload.items() if value is not None}


def resolve_code_snippet(
    snippet: str,
    documents: tuple[CodeDocument, ...],
    *,
    symbol_index: SymbolIndex | None = None,
    lexical_threshold: float = 0.5,
) -> SnippetResolution:
    """Resolve a code snippet without guessing between multiple targets."""

    if not snippet.strip():
        return SnippetResolution(
            status=ResolutionStatus.UNRESOLVED,
            candidates=(),
            unresolved_reason="code snippet is empty",
        )

    for document in documents:
        document.validate()

    stages = (
        _exact_candidates(snippet, documents),
        _normalized_candidates(snippet, documents),
        _lexical_candidates(snippet, documents, threshold=lexical_threshold),
        _symbol_candidates(snippet, symbol_index),
    )
    for candidates in stages:
        if candidates:
            return _finalize_resolution(candidates)

    return SnippetResolution(
        status=ResolutionStatus.UNRESOLVED,
        candidates=(),
        unresolved_reason="no exact, normalized, lexical, or symbol candidate matched",
    )


def normalize_code(text: str) -> str:
    """Remove comments and collapse whitespace for deterministic matching."""

    without_block_comments = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    without_line_comments = re.sub(r"(?m)(//|#).*$", " ", without_block_comments)
    return " ".join(without_line_comments.split())


def _exact_candidates(snippet: str, documents: tuple[CodeDocument, ...]) -> tuple[SnippetCandidate, ...]:
    return tuple(
        SnippetCandidate(
            document_id=document.document_id,
            file_path=document.file_path,
            match_kind=SnippetMatchKind.EXACT,
            score=1.0,
            reason="snippet text is an exact substring of the document",
        )
        for document in documents
        if snippet in document.content
    )


def _normalized_candidates(snippet: str, documents: tuple[CodeDocument, ...]) -> tuple[SnippetCandidate, ...]:
    normalized_snippet = normalize_code(snippet)
    if not normalized_snippet:
        return ()
    return tuple(
        SnippetCandidate(
            document_id=document.document_id,
            file_path=document.file_path,
            match_kind=SnippetMatchKind.NORMALIZED,
            score=0.92,
            reason="snippet matched after comment removal and whitespace normalization",
        )
        for document in documents
        if normalized_snippet in normalize_code(document.content)
    )


def _lexical_candidates(
    snippet: str,
    documents: tuple[CodeDocument, ...],
    *,
    threshold: float,
) -> tuple[SnippetCandidate, ...]:
    snippet_tokens = _code_tokens(snippet)
    if not snippet_tokens:
        return ()

    candidates: list[SnippetCandidate] = []
    for document in documents:
        document_tokens = _code_tokens(document.content)
        if not document_tokens:
            continue
        score = len(snippet_tokens & document_tokens) / len(snippet_tokens | document_tokens)
        if score >= threshold:
            candidates.append(
                SnippetCandidate(
                    document_id=document.document_id,
                    file_path=document.file_path,
                    match_kind=SnippetMatchKind.LEXICAL,
                    score=round(score, 4),
                    reason="token overlap exceeded the lexical similarity threshold",
                )
            )
    return tuple(sorted(candidates, key=lambda candidate: candidate.score, reverse=True))


def _symbol_candidates(snippet: str, symbol_index: SymbolIndex | None) -> tuple[SnippetCandidate, ...]:
    if symbol_index is None:
        return ()

    candidates_by_key: dict[tuple[str, str], SnippetCandidate] = {}
    for identifier in _identifiers(snippet):
        for symbol_candidate in symbol_index.find_by_symbol(identifier):
            candidate = _from_symbol_candidate(symbol_candidate)
            key = (candidate.document_id, candidate.symbol_id or "")
            previous = candidates_by_key.get(key)
            if previous is None or candidate.score > previous.score:
                candidates_by_key[key] = candidate

    return tuple(sorted(candidates_by_key.values(), key=lambda candidate: candidate.score, reverse=True))


def _from_symbol_candidate(candidate: SymbolCandidate) -> SnippetCandidate:
    return SnippetCandidate(
        document_id=candidate.record.symbol_id or candidate.record.file_path,
        file_path=candidate.record.file_path,
        match_kind=SnippetMatchKind.SYMBOL,
        score=round(candidate.score * 0.8, 4),
        reason="identifier from snippet matched the symbol index",
        symbol_id=candidate.record.symbol_id,
        qualified_name=candidate.record.qualified_name,
    )


def _finalize_resolution(candidates: tuple[SnippetCandidate, ...]) -> SnippetResolution:
    if len(candidates) == 1:
        return SnippetResolution(
            status=ResolutionStatus.RESOLVED,
            candidates=candidates,
            selected_candidate=candidates[0],
        )

    top_score = candidates[0].score
    tied = tuple(candidate for candidate in candidates if candidate.score == top_score)
    if len(tied) == 1 and top_score >= 0.75:
        return SnippetResolution(
            status=ResolutionStatus.RESOLVED,
            candidates=candidates,
            selected_candidate=tied[0],
        )

    return SnippetResolution(
        status=ResolutionStatus.AMBIGUOUS,
        candidates=candidates,
        ambiguity_reason="multiple target candidates matched; user clarification is required",
    )


def _code_tokens(text: str) -> set[str]:
    return {token.lower() for token in _identifiers(normalize_code(text))}


def _identifiers(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))
