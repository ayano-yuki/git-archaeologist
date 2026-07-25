"""Multi-stage retrieval planner with auditable route logs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class PlanStepKind(StrEnum):
    """Kinds of retrieval steps in the query plan."""

    SYMBOL_COMMITS = "symbol_commits"
    GRAPH_EXPANSION = "graph_expansion"
    SEARCH_CANDIDATES = "search_candidates"
    FILTER = "filter"


@dataclass(frozen=True)
class QueryTarget:
    """Resolved code target used as the retrieval starting point."""

    symbol_id: str | None = None
    file_path: str | None = None
    commit_shas: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "commit_shas", tuple(self.commit_shas))


@dataclass(frozen=True)
class EventCandidate:
    """Event retrieved from commits or graph expansion."""

    event_id: str
    event_kind: str
    occurred_at: datetime
    source_url: str
    file_path: str | None = None
    symbol_id: str | None = None
    related_event_ids: tuple[str, ...] = ()
    relationship_strength: float = 0.0

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        if not self.source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be an http or https URL")
        object.__setattr__(self, "related_event_ids", tuple(self.related_event_ids))


@dataclass(frozen=True)
class RetrievedCandidate:
    """Search result tied back to the route that produced it."""

    candidate_id: str
    event: EventCandidate
    score: float
    route: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id must be non-empty")
        object.__setattr__(self, "route", tuple(self.route))


@dataclass(frozen=True)
class QueryPlanStep:
    """One auditable step in multi-stage retrieval."""

    step_kind: PlanStepKind
    input_ids: tuple[str, ...]
    output_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_ids", tuple(self.input_ids))
        object.__setattr__(self, "output_ids", tuple(self.output_ids))


@dataclass(frozen=True)
class MultiStageSearchResult:
    """Final candidates plus the route log needed for debugging."""

    plan_steps: tuple[QueryPlanStep, ...]
    candidates: tuple[RetrievedCandidate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_steps", tuple(self.plan_steps))
        object.__setattr__(self, "candidates", tuple(self.candidates))


@dataclass(frozen=True)
class RetrievalFilter:
    """Filter by time and target scope."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    file_path: str | None = None
    symbol_id: str | None = None

    def matches(self, event: EventCandidate) -> bool:
        if self.start_time and event.occurred_at < self.start_time:
            return False
        if self.end_time and event.occurred_at > self.end_time:
            return False
        if self.file_path and event.file_path != self.file_path:
            return False
        if self.symbol_id and event.symbol_id != self.symbol_id:
            return False
        return True


class EventGraphBackend(Protocol):
    """Backend used to expand commits into related events."""

    def events_for_commits(self, commit_shas: tuple[str, ...]) -> tuple[EventCandidate, ...]:
        """Return commit events for the target symbol."""

    def expand(self, event_ids: tuple[str, ...]) -> tuple[EventCandidate, ...]:
        """Return related PR, Issue, Review, CI, Revert, or inferred events."""


class CandidateSearchBackend(Protocol):
    """Backend used to search chunks/events after graph expansion."""

    def search(self, query: str, events: tuple[EventCandidate, ...]) -> tuple[RetrievedCandidate, ...]:
        """Return ranked candidates from the supplied event scope."""


def run_multistage_search(
    query: str,
    target: QueryTarget,
    *,
    graph_backend: EventGraphBackend,
    search_backend: CandidateSearchBackend,
    retrieval_filter: RetrievalFilter | None = None,
) -> MultiStageSearchResult:
    """Search from symbol commits, through graph expansion, into ranked candidates."""

    plan_steps: list[QueryPlanStep] = []
    seed_events = graph_backend.events_for_commits(target.commit_shas)
    plan_steps.append(
        QueryPlanStep(
            step_kind=PlanStepKind.SYMBOL_COMMITS,
            input_ids=target.commit_shas,
            output_ids=tuple(event.event_id for event in seed_events),
            reason="seeded retrieval from target symbol commit history",
        )
    )

    expanded_events = graph_backend.expand(tuple(event.event_id for event in seed_events))
    plan_steps.append(
        QueryPlanStep(
            step_kind=PlanStepKind.GRAPH_EXPANSION,
            input_ids=tuple(event.event_id for event in seed_events),
            output_ids=tuple(event.event_id for event in expanded_events),
            reason="expanded commits through Event Graph relations",
        )
    )

    scoped_events = _filter_events((*seed_events, *expanded_events), retrieval_filter)
    if retrieval_filter is not None:
        plan_steps.append(
            QueryPlanStep(
                step_kind=PlanStepKind.FILTER,
                input_ids=tuple(event.event_id for event in (*seed_events, *expanded_events)),
                output_ids=tuple(event.event_id for event in scoped_events),
                reason="filtered events by time, file, or symbol scope",
            )
        )

    candidates = search_backend.search(query, scoped_events)
    plan_steps.append(
        QueryPlanStep(
            step_kind=PlanStepKind.SEARCH_CANDIDATES,
            input_ids=tuple(event.event_id for event in scoped_events),
            output_ids=tuple(candidate.candidate_id for candidate in candidates),
            reason="ranked candidates within the graph-expanded event scope",
        )
    )

    return MultiStageSearchResult(plan_steps=tuple(plan_steps), candidates=candidates)


def _filter_events(
    events: tuple[EventCandidate, ...],
    retrieval_filter: RetrievalFilter | None,
) -> tuple[EventCandidate, ...]:
    if retrieval_filter is None:
        return events
    return tuple(event for event in events if retrieval_filter.matches(event))
