"""Event graph relation generation for common events."""

from __future__ import annotations

from dataclasses import dataclass
import re

from git_archaeologist.normalization.common_events import (
    CommonEvent,
    EventRelation,
    EvidenceKind,
    RelationKind,
)


_ISSUE_REFERENCE_RE = re.compile(
    r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|#)\s*#(?P<number>\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GeneratedEdge:
    """Directed edge emitted from one source event."""

    source_event_id: str
    relation: EventRelation

    @property
    def target_event_id(self) -> str:
        return self.relation.target_event_id

    def to_dict(self) -> dict[str, object]:
        return {
            "source_event_id": self.source_event_id,
            "target_event_id": self.target_event_id,
            "relation": self.relation.to_dict(),
        }


def generate_event_graph_edges(events: tuple[CommonEvent, ...]) -> tuple[GeneratedEdge, ...]:
    """Generate explicit and inferred graph edges from common events."""

    by_commit = {
        event.observed.commit_sha: event
        for event in events
        if event.observed.commit_sha and event.evidence_kind == EvidenceKind.GIT_COMMIT
    }
    by_issue = {
        event.observed.issue_number: event
        for event in events
        if event.observed.issue_number is not None
    }

    edges: list[GeneratedEdge] = []
    for event in events:
        edges.extend(_merge_sha_edges(event, by_commit))
        edges.extend(_ci_head_sha_edges(event, by_commit))
        edges.extend(_issue_reference_edges(event, by_issue))
        edges.extend(_file_overlap_edges(event, events))
    return tuple(_dedupe_edges(edges))


def _merge_sha_edges(
    event: CommonEvent,
    by_commit: dict[str, CommonEvent],
) -> tuple[GeneratedEdge, ...]:
    sha = event.extracted.commit_sha or event.observed.commit_sha
    if event.observed.pull_request_number is None or not sha:
        return ()
    target = by_commit.get(sha)
    if target is None or target.event_id == event.event_id:
        return ()
    return (
        GeneratedEdge(
            source_event_id=event.event_id,
            relation=EventRelation(
                relation_kind=RelationKind.IMPLEMENTS,
                target_event_id=target.event_id,
                evidence_kind=EvidenceKind.GITHUB_PULL_REQUEST,
                source_url=event.source_url,
                rationale="PR merge/head SHA matched a collected commit SHA.",
            ),
        ),
    )


def _ci_head_sha_edges(
    event: CommonEvent,
    by_commit: dict[str, CommonEvent],
) -> tuple[GeneratedEdge, ...]:
    sha = event.observed.commit_sha or event.extracted.commit_sha
    if event.evidence_kind != EvidenceKind.GITHUB_ACTIONS_RUN or not sha:
        return ()
    target = by_commit.get(sha)
    if target is None or target.event_id == event.event_id:
        return ()
    return (
        GeneratedEdge(
            source_event_id=event.event_id,
            relation=EventRelation(
                relation_kind=RelationKind.TRIGGERS,
                target_event_id=target.event_id,
                evidence_kind=EvidenceKind.GITHUB_ACTIONS_RUN,
                source_url=event.source_url,
                rationale="Workflow head SHA matched a collected commit SHA.",
            ),
        ),
    )


def _issue_reference_edges(
    event: CommonEvent,
    by_issue: dict[int, CommonEvent],
) -> tuple[GeneratedEdge, ...]:
    text = "\n".join(
        part
        for part in (
            event.observed.title,
            event.observed.body,
            event.extracted.body,
        )
        if part
    )
    edges: list[GeneratedEdge] = []
    for match in _ISSUE_REFERENCE_RE.finditer(text):
        issue_number = int(match.group("number"))
        target = by_issue.get(issue_number)
        if target is None or target.event_id == event.event_id:
            continue
        relation_kind = (
            RelationKind.CLOSES
            if match.group(0).lower().startswith(("close", "fix", "resolve"))
            else RelationKind.MENTIONS
        )
        edges.append(
            GeneratedEdge(
                source_event_id=event.event_id,
                relation=EventRelation(
                    relation_kind=relation_kind,
                    target_event_id=target.event_id,
                    evidence_kind=event.evidence_kind,
                    source_url=event.source_url,
                    rationale=f"Text explicitly referenced issue #{issue_number}.",
                ),
            )
        )
    return tuple(edges)


def _file_overlap_edges(
    event: CommonEvent,
    events: tuple[CommonEvent, ...],
) -> tuple[GeneratedEdge, ...]:
    file_path = event.observed.file_path or event.extracted.file_path
    if not file_path:
        return ()
    edges: list[GeneratedEdge] = []
    for target in events:
        if target.event_id == event.event_id:
            continue
        target_file = target.observed.file_path or target.extracted.file_path
        if target_file != file_path:
            continue
        edges.append(
            GeneratedEdge(
                source_event_id=event.event_id,
                relation=EventRelation(
                    relation_kind=RelationKind.POSSIBLY_RELATED,
                    target_event_id=target.event_id,
                    evidence_kind=event.evidence_kind,
                    confidence=0.4,
                    source_url=event.source_url,
                    rationale="Events touch the same file; this is only an inferred relation.",
                    inferred=True,
                ),
            )
        )
    return tuple(edges)


def _dedupe_edges(edges: list[GeneratedEdge]) -> tuple[GeneratedEdge, ...]:
    seen: set[tuple[str, str, RelationKind]] = set()
    deduped: list[GeneratedEdge] = []
    for edge in edges:
        key = (edge.source_event_id, edge.target_event_id, edge.relation.relation_kind)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(edge)
    return tuple(deduped)
