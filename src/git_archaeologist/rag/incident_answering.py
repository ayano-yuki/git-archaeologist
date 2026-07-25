"""Incident answers and historical-risk checks grounded in incident graphs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from git_archaeologist.normalization.incident_graph import (
    ConstraintState,
    IncidentGraph,
)


class IncidentAnswerStatus(StrEnum):
    """Whether an incident answer can state a cause."""

    ANSWERED = "answered"
    UNKNOWN_CAUSE = "unknown_cause"


@dataclass(frozen=True)
class IncidentAnswer:
    """Structured answer format for Phase3 incident analysis."""

    status: IncidentAnswerStatus
    timeline: tuple[dict[str, object], ...]
    observed_cause: str | None
    inferred_cause: str | None
    fix: str | None
    remaining_constraint: str
    related_failures: tuple[str, ...]
    citations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class HistoricalRiskFinding:
    """Risk signal from a current change against prior incidents."""

    risk_found: bool
    reason: str
    supporting_incident_ids: tuple[str, ...]
    suppressed_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_incident_answer(graph: IncidentGraph) -> IncidentAnswer:
    """Build an answer that separates observed cause, inference, and unknowns."""

    timeline = tuple(node.to_dict() for node in graph.timeline())
    citations = tuple(node.event_id for node in graph.timeline() if node.source_url)
    failure_nodes = tuple(node for node in graph.nodes if node.kind == "ci_failure")
    fix_nodes = tuple(node for node in graph.nodes if node.kind in {"fix", "revert", "reapply"})
    if not failure_nodes:
        return IncidentAnswer(
            status=IncidentAnswerStatus.UNKNOWN_CAUSE,
            timeline=timeline,
            observed_cause=None,
            inferred_cause=None,
            fix=None,
            remaining_constraint=graph.constraint_rationale,
            related_failures=(),
            citations=citations,
        )

    observed_cause = "The timeline confirms a CI failure after the introducing change."
    inferred_cause = None
    if graph.constraint_state is ConstraintState.UNKNOWN:
        observed_cause = None
        inferred_cause = "The available evidence is only temporal; no direct cause should be asserted."
    return IncidentAnswer(
        status=IncidentAnswerStatus.ANSWERED if observed_cause else IncidentAnswerStatus.UNKNOWN_CAUSE,
        timeline=timeline,
        observed_cause=observed_cause,
        inferred_cause=inferred_cause,
        fix=fix_nodes[0].title if fix_nodes else None,
        remaining_constraint=graph.constraint_rationale,
        related_failures=tuple(node.event_id for node in failure_nodes),
        citations=citations,
    )


def evaluate_historical_risk(
    *,
    changed_files: tuple[str, ...],
    changed_symbols: tuple[str, ...],
    failure_signature_ids: tuple[str, ...],
    incident_graphs: tuple[IncidentGraph, ...],
) -> HistoricalRiskFinding:
    """Warn only when a current change overlaps concrete incident evidence."""

    supporting: list[str] = []
    for graph in incident_graphs:
        graph_files = {node.file_path for node in graph.nodes if node.file_path}
        graph_symbols = {node.symbol_name for node in graph.nodes if node.symbol_name}
        graph_failure_ids = {node.event_id for node in graph.nodes if node.kind == "ci_failure"}
        concrete_symbol_overlap = bool(set(changed_symbols) & graph_symbols)
        concrete_failure_overlap = bool(set(failure_signature_ids) & graph_failure_ids)
        if concrete_symbol_overlap or concrete_failure_overlap:
            supporting.append(graph.incident_id)
            continue
        if set(changed_files) & graph_files:
            return HistoricalRiskFinding(
                risk_found=False,
                reason="File overlap alone is insufficient for a high-risk warning.",
                supporting_incident_ids=(),
                suppressed_reason="same_file_only",
            )
    if supporting:
        return HistoricalRiskFinding(
            risk_found=True,
            reason="The change overlaps a symbol or failure signature with prior incident evidence.",
            supporting_incident_ids=tuple(supporting),
        )
    return HistoricalRiskFinding(
        risk_found=False,
        reason="No concrete historical incident overlap was found.",
        supporting_incident_ids=(),
    )
