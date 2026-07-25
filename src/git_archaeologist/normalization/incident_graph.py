"""Incident graph and Revert analysis for Phase3."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import re


class IncidentRelationKind(StrEnum):
    """Incident edge meanings with causality provenance."""

    INTRODUCED = "introduced"
    DETECTED_BY = "detected_by"
    FIXED_BY = "fixed_by"
    REVERTED_BY = "reverted_by"
    REAPPLIED_BY = "reapplied_by"
    RELATED_REVIEW = "related_review"


class CausalityProvenance(StrEnum):
    """Whether an incident edge is directly observed or inferred."""

    OBSERVED = "observed"
    INFERRED = "inferred"


class RevertState(StrEnum):
    """Revert classification used by answers and risk checks."""

    NOT_REVERT = "not_revert"
    REVERTED = "reverted"
    PARTIALLY_REVERTED = "partially_reverted"
    REAPPLIED = "reapplied"


class ConstraintState(StrEnum):
    """Whether an old mitigation still matters for current changes."""

    MAINTAINED = "maintained"
    REPLACED = "replaced"
    RESOLVED = "resolved"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IncidentNode:
    """One event participating in an incident timeline."""

    event_id: str
    kind: str
    occurred_at: str
    title: str
    file_path: str | None = None
    symbol_name: str | None = None
    source_url: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class IncidentEdge:
    """Observed or inferred relationship between incident nodes."""

    source_event_id: str
    target_event_id: str
    relation_kind: IncidentRelationKind
    provenance: CausalityProvenance
    confidence: float
    rationale: str

    def __post_init__(self) -> None:
        if self.provenance is CausalityProvenance.INFERRED and self.confidence >= 1.0:
            raise ValueError("inferred incident edges must use confidence below 1.0")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["relation_kind"] = self.relation_kind.value
        payload["provenance"] = self.provenance.value
        return payload


@dataclass(frozen=True)
class RevertDetection:
    """Revert, partial revert, or reapply detection result."""

    state: RevertState
    reverted_commit_sha: str | None
    confidence: float
    rationale: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


@dataclass(frozen=True)
class IncidentGraph:
    """Timeline graph for one incident."""

    incident_id: str
    nodes: tuple[IncidentNode, ...]
    edges: tuple[IncidentEdge, ...]
    constraint_state: ConstraintState
    constraint_rationale: str

    def timeline(self) -> tuple[IncidentNode, ...]:
        return tuple(sorted(self.nodes, key=lambda node: node.occurred_at))

    def to_dict(self) -> dict[str, object]:
        return {
            "incident_id": self.incident_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "constraint_state": self.constraint_state.value,
            "constraint_rationale": self.constraint_rationale,
        }


_REVERT_SHA_RE = re.compile(r"this reverts commit (?P<sha>[0-9a-f]{7,40})", re.IGNORECASE)
_REAPPLY_RE = re.compile(r"\b(reapply|reland)\b", re.IGNORECASE)


def detect_revert_state(
    commit_message: str,
    *,
    patch_reverse_similarity: float | None = None,
    reapplied_later: bool = False,
) -> RevertDetection:
    """Classify a commit message and optional patch signal."""

    sha_match = _REVERT_SHA_RE.search(commit_message)
    looks_like_revert = commit_message.lower().startswith("revert") or sha_match is not None
    if reapplied_later or _REAPPLY_RE.search(commit_message):
        return RevertDetection(RevertState.REAPPLIED, sha_match.group("sha") if sha_match else None, 1.0, "Commit explicitly reapplies or relands a reverted change.")
    if not looks_like_revert:
        return RevertDetection(RevertState.NOT_REVERT, None, 0.0, "No explicit revert markers were found.")
    if patch_reverse_similarity is not None and patch_reverse_similarity < 0.85:
        return RevertDetection(RevertState.PARTIALLY_REVERTED, sha_match.group("sha") if sha_match else None, 0.7, "Revert marker exists but patch inverse similarity is below the full-revert threshold.")
    return RevertDetection(RevertState.REVERTED, sha_match.group("sha") if sha_match else None, 1.0, "Commit message explicitly indicates a revert.")


def build_incident_graph(
    *,
    incident_id: str,
    introducing_change: IncidentNode,
    failure: IncidentNode,
    fix: IncidentNode | None = None,
    revert: IncidentNode | None = None,
    reapply: IncidentNode | None = None,
    related_reviews: tuple[IncidentNode, ...] = (),
) -> IncidentGraph:
    """Connect introduction, detection, fix, revert, and reapply nodes."""

    nodes = [introducing_change, failure, *related_reviews]
    edges = [
        IncidentEdge(
            introducing_change.event_id,
            failure.event_id,
            IncidentRelationKind.DETECTED_BY,
            CausalityProvenance.OBSERVED,
            1.0,
            "Failure event references the introducing change head SHA or explicit CI run.",
        )
    ]
    for review in related_reviews:
        edges.append(
            IncidentEdge(
                review.event_id,
                introducing_change.event_id,
                IncidentRelationKind.RELATED_REVIEW,
                CausalityProvenance.OBSERVED,
                1.0,
                "Review is explicitly linked to the change under analysis.",
            )
        )
    if fix is not None:
        nodes.append(fix)
        edges.append(
            IncidentEdge(failure.event_id, fix.event_id, IncidentRelationKind.FIXED_BY, CausalityProvenance.OBSERVED, 1.0, "Fix is explicitly linked to the failure.")
        )
    if revert is not None:
        nodes.append(revert)
        edges.append(
            IncidentEdge(introducing_change.event_id, revert.event_id, IncidentRelationKind.REVERTED_BY, CausalityProvenance.OBSERVED, 1.0, "Revert explicitly references the introducing change.")
        )
    if reapply is not None:
        nodes.append(reapply)
        source = revert.event_id if revert is not None else introducing_change.event_id
        edges.append(
            IncidentEdge(source, reapply.event_id, IncidentRelationKind.REAPPLIED_BY, CausalityProvenance.OBSERVED, 1.0, "Reapply explicitly relands the reverted behavior.")
        )

    state, rationale = determine_constraint_state(fix=fix, revert=revert, reapply=reapply, related_reviews=related_reviews)
    return IncidentGraph(incident_id, tuple(nodes), tuple(edges), state, rationale)


def determine_constraint_state(
    *,
    fix: IncidentNode | None,
    revert: IncidentNode | None,
    reapply: IncidentNode | None,
    related_reviews: tuple[IncidentNode, ...] = (),
) -> tuple[ConstraintState, str]:
    """Classify whether the mitigation still applies today."""

    if reapply is not None:
        return ConstraintState.MAINTAINED, "A later reapply keeps the constraint active."
    if revert is not None and fix is None:
        return ConstraintState.RESOLVED, "The change was reverted and no replacement fix is recorded."
    if fix is not None:
        if any("replace" in review.title.lower() for review in related_reviews):
            return ConstraintState.REPLACED, "A linked review records a replacement mitigation."
        return ConstraintState.MAINTAINED, "A fix is recorded and no later removal is known."
    return ConstraintState.UNKNOWN, "No fix, revert, or reapply evidence is available."
