"""Deterministic target resolver for repository questions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Protocol

from git_archaeologist.search.code_snippet_resolver import CodeDocument, ResolutionStatus, resolve_code_snippet
from git_archaeologist.search.symbol_index import SymbolCandidate, SymbolIndex


class TargetKind(StrEnum):
    """Repository target kinds understood by the resolver."""

    PULL_REQUEST = "pull_request"
    FILE = "file"
    SYMBOL = "symbol"
    CODE_SNIPPET = "code_snippet"
    GIT_LOG_STRING = "git_log_string"
    GIT_LOG_REGEX = "git_log_regex"


class TargetResolutionStatus(StrEnum):
    """Final target resolution state."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class PullRequestReference:
    """Parsed GitHub pull request URL."""

    repository: str
    number: int
    url: str

    @property
    def identifier(self) -> str:
        return f"{self.repository}#{self.number}"


@dataclass(frozen=True)
class GitLogMatch:
    """Match returned by a git log -S or -G style backend."""

    commit_sha: str
    file_path: str
    query: str
    mode: TargetKind
    confidence: float = 0.6


class GitLogSearchBackend(Protocol):
    """Boundary for git log -S and -G searches."""

    def search_string(self, query: str) -> tuple[GitLogMatch, ...]:
        """Return candidates from git log -S."""

    def search_regex(self, query: str) -> tuple[GitLogMatch, ...]:
        """Return candidates from git log -G."""


@dataclass(frozen=True)
class TargetRequest:
    """Structured request produced by input interpretation."""

    raw_text: str
    pr_url: str | None = None
    file_path: str | None = None
    symbol_name: str | None = None
    code_snippet: str | None = None
    git_log_string: str | None = None
    git_log_regex: str | None = None


@dataclass(frozen=True)
class TargetCandidate:
    """A target candidate with confidence and inspectable adoption reason."""

    target_kind: TargetKind
    identifier: str
    confidence: float
    reason: str
    file_path: str | None = None
    symbol_id: str | None = None
    qualified_name: str | None = None
    commit_sha: str | None = None
    pull_request: PullRequestReference | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "target_kind": self.target_kind.value,
            "identifier": self.identifier,
            "confidence": self.confidence,
            "reason": self.reason,
            "file_path": self.file_path,
            "symbol_id": self.symbol_id,
            "qualified_name": self.qualified_name,
            "commit_sha": self.commit_sha,
            "pull_request": self.pull_request.__dict__ if self.pull_request else None,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class TargetResolution:
    """Resolver result that prevents generation when the target is unsafe."""

    status: TargetResolutionStatus
    candidates: tuple[TargetCandidate, ...]
    selected_candidate: TargetCandidate | None = None
    unresolved_reason: str | None = None
    clarification_reason: str | None = None

    @property
    def should_generate_answer(self) -> bool:
        return self.status is TargetResolutionStatus.RESOLVED and self.selected_candidate is not None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "status": self.status.value,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "selected_candidate": self.selected_candidate.to_dict() if self.selected_candidate else None,
            "unresolved_reason": self.unresolved_reason,
            "clarification_reason": self.clarification_reason,
            "should_generate_answer": self.should_generate_answer,
        }
        return {key: value for key, value in payload.items() if value is not None}


def resolve_target(
    request: TargetRequest,
    *,
    current_documents: tuple[CodeDocument, ...] = (),
    symbol_index: SymbolIndex | None = None,
    git_log_backend: GitLogSearchBackend | None = None,
) -> TargetResolution:
    """Resolve a repository target in deterministic precedence order."""

    for candidate_stage in (
        _pull_request_candidates(request),
        _file_candidates(request, current_documents, symbol_index),
        _symbol_candidates(request, symbol_index),
        _snippet_candidates(request, current_documents, symbol_index),
        _git_log_string_candidates(request, git_log_backend),
        _git_log_regex_candidates(request, git_log_backend),
    ):
        if candidate_stage:
            return _finalize(candidate_stage)

    return TargetResolution(
        status=TargetResolutionStatus.UNRESOLVED,
        candidates=(),
        unresolved_reason="no PR URL, file, symbol, code snippet, or git log candidate resolved",
    )


def parse_pull_request_url(text: str) -> PullRequestReference | None:
    """Parse a GitHub pull request URL if one is present."""

    match = re.search(r"https://github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)", text)
    if match is None:
        return None
    return PullRequestReference(
        repository=match.group(1),
        number=int(match.group(2)),
        url=match.group(0),
    )


def _pull_request_candidates(request: TargetRequest) -> tuple[TargetCandidate, ...]:
    reference = parse_pull_request_url(request.pr_url or request.raw_text)
    if reference is None:
        return ()
    return (
        TargetCandidate(
            target_kind=TargetKind.PULL_REQUEST,
            identifier=reference.identifier,
            confidence=1.0,
            reason="GitHub pull request URL was parsed deterministically",
            pull_request=reference,
        ),
    )


def _file_candidates(
    request: TargetRequest,
    documents: tuple[CodeDocument, ...],
    symbol_index: SymbolIndex | None,
) -> tuple[TargetCandidate, ...]:
    if not request.file_path:
        return ()

    candidates: list[TargetCandidate] = []
    for document in documents:
        if document.file_path == request.file_path:
            candidates.append(
                TargetCandidate(
                    target_kind=TargetKind.FILE,
                    identifier=document.file_path,
                    confidence=0.95,
                    reason="file path matched current code document",
                    file_path=document.file_path,
                    commit_sha=document.commit_sha,
                )
            )

    if symbol_index is not None:
        candidates.extend(_from_symbol_candidates(symbol_index.find_by_file(request.file_path), TargetKind.FILE))

    return _dedupe(candidates)


def _symbol_candidates(request: TargetRequest, symbol_index: SymbolIndex | None) -> tuple[TargetCandidate, ...]:
    if not request.symbol_name or symbol_index is None:
        return ()
    return _from_symbol_candidates(symbol_index.find_by_symbol(request.symbol_name), TargetKind.SYMBOL)


def _snippet_candidates(
    request: TargetRequest,
    documents: tuple[CodeDocument, ...],
    symbol_index: SymbolIndex | None,
) -> tuple[TargetCandidate, ...]:
    if not request.code_snippet:
        return ()

    snippet_resolution = resolve_code_snippet(
        request.code_snippet,
        documents,
        symbol_index=symbol_index,
    )
    if snippet_resolution.status is ResolutionStatus.UNRESOLVED:
        return ()

    return tuple(
        TargetCandidate(
            target_kind=TargetKind.CODE_SNIPPET,
            identifier=candidate.symbol_id or candidate.file_path,
            confidence=candidate.score,
            reason=candidate.reason,
            file_path=candidate.file_path,
            symbol_id=candidate.symbol_id,
            qualified_name=candidate.qualified_name,
        )
        for candidate in snippet_resolution.candidates
    )


def _git_log_string_candidates(
    request: TargetRequest,
    backend: GitLogSearchBackend | None,
) -> tuple[TargetCandidate, ...]:
    if backend is None:
        return ()
    query = request.git_log_string or request.code_snippet
    if not query:
        return ()
    return _from_git_log_matches(backend.search_string(query))


def _git_log_regex_candidates(
    request: TargetRequest,
    backend: GitLogSearchBackend | None,
) -> tuple[TargetCandidate, ...]:
    if backend is None or not request.git_log_regex:
        return ()
    return _from_git_log_matches(backend.search_regex(request.git_log_regex))


def _from_symbol_candidates(
    candidates: tuple[SymbolCandidate, ...],
    target_kind: TargetKind,
) -> tuple[TargetCandidate, ...]:
    return tuple(
        TargetCandidate(
            target_kind=target_kind,
            identifier=candidate.record.symbol_id or candidate.record.file_path,
            confidence=candidate.score,
            reason=f"{candidate.match_kind.value} from symbol index",
            file_path=candidate.record.file_path,
            symbol_id=candidate.record.symbol_id,
            qualified_name=candidate.record.qualified_name,
            commit_sha=candidate.record.commit_sha,
        )
        for candidate in candidates
    )


def _from_git_log_matches(matches: tuple[GitLogMatch, ...]) -> tuple[TargetCandidate, ...]:
    return tuple(
        TargetCandidate(
            target_kind=match.mode,
            identifier=f"{match.commit_sha}:{match.file_path}",
            confidence=match.confidence,
            reason=f"{match.mode.value} matched git history",
            file_path=match.file_path,
            commit_sha=match.commit_sha,
        )
        for match in matches
    )


def _finalize(candidates: tuple[TargetCandidate, ...]) -> TargetResolution:
    ordered = tuple(sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True))
    if len(ordered) == 1:
        return TargetResolution(
            status=TargetResolutionStatus.RESOLVED,
            candidates=ordered,
            selected_candidate=ordered[0],
        )

    top_confidence = ordered[0].confidence
    tied = tuple(candidate for candidate in ordered if candidate.confidence == top_confidence)
    if len(tied) == 1 and top_confidence >= 0.8:
        return TargetResolution(
            status=TargetResolutionStatus.RESOLVED,
            candidates=ordered,
            selected_candidate=tied[0],
        )

    return TargetResolution(
        status=TargetResolutionStatus.AMBIGUOUS,
        candidates=ordered,
        clarification_reason="multiple target candidates remain; ask the user to choose before answering",
    )


def _dedupe(candidates: Iterable[TargetCandidate]) -> tuple[TargetCandidate, ...]:
    by_key: dict[tuple[TargetKind, str], TargetCandidate] = {}
    for candidate in candidates:
        key = (candidate.target_kind, f"{candidate.identifier}@{candidate.commit_sha or ''}")
        previous = by_key.get(key)
        if previous is None or candidate.confidence > previous.confidence:
            by_key[key] = candidate
    return tuple(by_key.values())
