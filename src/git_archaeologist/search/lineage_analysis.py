"""Line and condition lineage analysis for Phase4."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import re


class LineageRelationKind(StrEnum):
    """How a later code location relates to an earlier one."""

    SAME = "same"
    RENAMED = "renamed"
    MOVED = "moved"
    COPIED = "copied"
    SPLIT = "split"
    MERGED = "merged"
    REFACTORED = "refactored"
    UNKNOWN = "unknown"


class ConditionChangeKind(StrEnum):
    """Semantic category for a condition expression change."""

    ADDED = "added"
    REMOVED = "removed"
    NEGATED = "negated"
    EXTENDED = "extended"
    REORDERED = "reordered"
    FORMAT_ONLY = "format_only"


@dataclass(frozen=True)
class LineRange:
    """Inclusive line range in a file at one revision."""

    file_path: str
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("line range must be positive and ordered")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LineOriginCandidate:
    """Candidate commit that last introduced or modified a line range."""

    commit_sha: str
    current_range: LineRange
    original_range: LineRange
    confidence: float
    evidence: str
    boundary: bool = False
    merge_commit: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FileLineageEdge:
    """Path history edge across rename, move, copy, or refactor."""

    source_path: str
    target_path: str
    relation_kind: LineageRelationKind
    confidence: float
    rationale: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["relation_kind"] = self.relation_kind.value
        return payload


@dataclass(frozen=True)
class SymbolLineageEdge:
    """Symbol history edge across rename, split, merge, copy, or refactor."""

    source_symbol: str
    target_symbol: str
    relation_kind: LineageRelationKind
    confidence: float
    evidence: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["relation_kind"] = self.relation_kind.value
        return payload


@dataclass(frozen=True)
class ConditionHistoryEntry:
    """Condition expression change with branch and test context."""

    commit_sha: str
    file_path: str
    symbol_name: str
    before_expression: str | None
    after_expression: str | None
    change_kind: ConditionChangeKind
    branch_body_excerpt: str
    related_tests: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["change_kind"] = self.change_kind.value
        return payload


@dataclass(frozen=True)
class RationaleSeparation:
    """Introduction and maintenance rationale must stay separate."""

    introduction_rationale: str | None
    maintenance_rationale: str | None
    current_state: str
    missing_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_blame_porcelain(
    blame_text: str,
    *,
    file_path: str,
    requested_start: int,
    requested_end: int,
) -> tuple[LineOriginCandidate, ...]:
    """Parse a minimal porcelain blame excerpt into line origin candidates."""

    candidates: list[LineOriginCandidate] = []
    current_sha: str | None = None
    original_line: int | None = None
    current_line: int | None = None
    boundary = False
    for line in blame_text.splitlines():
        header = re.match(r"^(?P<sha>[0-9a-f]{7,40}) (?P<orig>\d+) (?P<cur>\d+)", line)
        if header:
            current_sha = header.group("sha")
            original_line = int(header.group("orig"))
            current_line = int(header.group("cur"))
            boundary = False
            continue
        if line == "boundary":
            boundary = True
            continue
        if line.startswith("\t") and current_sha and original_line and current_line:
            if requested_start <= current_line <= requested_end:
                line_range = LineRange(file_path, current_line, current_line)
                candidates.append(
                    LineOriginCandidate(
                        commit_sha=current_sha,
                        current_range=line_range,
                        original_range=LineRange(file_path, original_line, original_line),
                        confidence=0.7 if boundary else 1.0,
                        evidence="git blame porcelain",
                        boundary=boundary,
                    )
                )
    return tuple(candidates)


def detect_file_lineage(
    *,
    source_path: str,
    target_path: str,
    source_content: str,
    target_content: str,
    explicit_rename: bool = False,
) -> FileLineageEdge:
    """Detect file rename, move, copy, or refactor from path and content similarity."""

    similarity = _jaccard_tokens(source_content, target_content)
    if explicit_rename:
        kind = LineageRelationKind.RENAMED
        confidence = 1.0
    elif source_path != target_path and similarity >= 0.9:
        kind = LineageRelationKind.MOVED
        confidence = similarity
    elif source_path != target_path and similarity >= 0.65:
        kind = LineageRelationKind.COPIED
        confidence = similarity
    elif similarity >= 0.45:
        kind = LineageRelationKind.REFACTORED
        confidence = similarity
    else:
        kind = LineageRelationKind.UNKNOWN
        confidence = similarity
    return FileLineageEdge(source_path, target_path, kind, round(confidence, 3), "Path and token similarity were compared.")


def detect_symbol_lineage(
    *,
    source_symbol: str,
    target_symbol: str,
    source_body: str,
    target_body: str,
) -> SymbolLineageEdge:
    """Detect symbol rename, copy, split/merge, refactor, or unknown lineage."""

    similarity = _jaccard_tokens(source_body, target_body)
    if source_symbol != target_symbol and similarity >= 0.85:
        kind = LineageRelationKind.RENAMED
    elif similarity >= 0.85:
        kind = LineageRelationKind.SAME
    elif similarity >= 0.55:
        kind = LineageRelationKind.REFACTORED
    else:
        kind = LineageRelationKind.UNKNOWN
    return SymbolLineageEdge(source_symbol, target_symbol, kind, round(similarity, 3), "Symbol body token similarity and name continuity were compared.")


def classify_condition_change(before: str | None, after: str | None) -> ConditionChangeKind:
    """Classify a condition expression change without relying on formatting."""

    if before is None and after is not None:
        return ConditionChangeKind.ADDED
    if before is not None and after is None:
        return ConditionChangeKind.REMOVED
    if before is None or after is None:
        return ConditionChangeKind.FORMAT_ONLY
    normalized_before = _normalize_condition(before)
    normalized_after = _normalize_condition(after)
    if normalized_before == normalized_after:
        return ConditionChangeKind.FORMAT_ONLY
    if normalized_after in {f"!({normalized_before})", f"!{normalized_before}"}:
        return ConditionChangeKind.NEGATED
    before_terms = set(_condition_terms(normalized_before))
    after_terms = set(_condition_terms(normalized_after))
    if before_terms < after_terms:
        return ConditionChangeKind.EXTENDED
    if before_terms == after_terms:
        return ConditionChangeKind.REORDERED
    return ConditionChangeKind.EXTENDED


def build_condition_history_entry(
    *,
    commit_sha: str,
    file_path: str,
    symbol_name: str,
    before_expression: str | None,
    after_expression: str | None,
    branch_body_excerpt: str,
    related_tests: tuple[str, ...] = (),
) -> ConditionHistoryEntry:
    """Create a condition history entry with related test evidence."""

    return ConditionHistoryEntry(
        commit_sha=commit_sha,
        file_path=file_path,
        symbol_name=symbol_name,
        before_expression=before_expression,
        after_expression=after_expression,
        change_kind=classify_condition_change(before_expression, after_expression),
        branch_body_excerpt=branch_body_excerpt,
        related_tests=tuple(related_tests),
    )


def separate_rationale(
    *,
    introduction_evidence: str | None,
    maintenance_evidence: str | None,
    current_state: str,
) -> RationaleSeparation:
    """Keep introduction and maintenance rationale independent."""

    if introduction_evidence is None or maintenance_evidence is None:
        return RationaleSeparation(
            introduction_rationale=introduction_evidence,
            maintenance_rationale=maintenance_evidence,
            current_state=current_state,
            missing_reason="introduction or maintenance evidence is missing",
        )
    return RationaleSeparation(introduction_evidence, maintenance_evidence, current_state)


def content_fingerprint(text: str) -> str:
    """Return a normalized content fingerprint for copied-code candidates."""

    return hashlib.sha256(" ".join(_tokens(text)).encode("utf-8")).hexdigest()[:16]


def _jaccard_tokens(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+", text.lower()))


def _normalize_condition(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _condition_terms(value: str) -> tuple[str, ...]:
    return tuple(term for term in re.split(r"&&|\|\|", value) if term)
