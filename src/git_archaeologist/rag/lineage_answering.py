"""Ambiguity-aware answers for line and condition lineage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from git_archaeologist.search.lineage_analysis import (
    ConditionHistoryEntry,
    LineOriginCandidate,
    RationaleSeparation,
)


class LineageAnswerStatus(StrEnum):
    """Whether lineage can be answered uniquely."""

    ANSWERED = "answered"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LineageCandidateSummary:
    """Human-facing candidate with support and contradictions."""

    candidate_id: str
    confidence: float
    supporting_events: tuple[str, ...]
    contradictions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LineageAnswer:
    """Answer that separates origin, maintenance, tests, and ambiguity."""

    status: LineageAnswerStatus
    introduction_rationale: str | None
    maintenance_rationale: str | None
    current_state: str
    related_tests: tuple[str, ...]
    candidates: tuple[LineageCandidateSummary, ...]
    missing_information: str | None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def build_lineage_answer(
    *,
    origin_candidates: tuple[LineOriginCandidate, ...],
    rationale: RationaleSeparation,
    condition_history: tuple[ConditionHistoryEntry, ...] = (),
) -> LineageAnswer:
    """Build a lineage answer without forcing one candidate when ambiguous."""

    candidate_summaries = tuple(_candidate_summary(candidate) for candidate in origin_candidates)
    related_tests = tuple(
        test_id
        for entry in condition_history
        for test_id in entry.related_tests
    )
    if not origin_candidates:
        return LineageAnswer(
            status=LineageAnswerStatus.UNKNOWN,
            introduction_rationale=None,
            maintenance_rationale=rationale.maintenance_rationale,
            current_state=rationale.current_state,
            related_tests=related_tests,
            candidates=(),
            missing_information="No line origin candidate was available.",
        )
    top_confidence = max(candidate.confidence for candidate in origin_candidates)
    top_candidates = tuple(candidate for candidate in origin_candidates if candidate.confidence == top_confidence)
    ambiguous = len(top_candidates) > 1 or rationale.missing_reason is not None
    return LineageAnswer(
        status=LineageAnswerStatus.AMBIGUOUS if ambiguous else LineageAnswerStatus.ANSWERED,
        introduction_rationale=rationale.introduction_rationale,
        maintenance_rationale=rationale.maintenance_rationale,
        current_state=rationale.current_state,
        related_tests=related_tests,
        candidates=candidate_summaries,
        missing_information=rationale.missing_reason if ambiguous else None,
    )


def _candidate_summary(candidate: LineOriginCandidate) -> LineageCandidateSummary:
    contradictions = ("boundary commit lowers confidence",) if candidate.boundary else ()
    return LineageCandidateSummary(
        candidate_id=f"{candidate.commit_sha}:{candidate.original_range.file_path}:{candidate.original_range.start_line}",
        confidence=candidate.confidence,
        supporting_events=(candidate.commit_sha,),
        contradictions=contradictions,
    )
