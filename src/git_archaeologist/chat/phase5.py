"""Phase5 chat routing, unified citations, and session freshness."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from git_archaeologist.chat.chat_flow import ChatEvidencePack, ChatTarget
from git_archaeologist.chat.input_interpreter import (
    InterpretedInput,
    QueryIntent,
    interpret_input,
)


class Phase5Route(StrEnum):
    """Integrated chat routes across all completed feature families."""

    IMPLEMENTATION_RATIONALE = "implementation_rationale"
    CHANGE_RISK = "change_risk"
    INCIDENT_ANALYSIS = "incident_analysis"
    LINEAGE_ANALYSIS = "lineage_analysis"
    COMBINED = "combined"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class UnifiedQueryPlan:
    """Routing result for a Phase5 chat turn."""

    route: Phase5Route
    query_plan_ids: tuple[str, ...]
    requires_current_change: bool
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_plan_ids", tuple(self.query_plan_ids))
        if not self.query_plan_ids and self.route not in {
            Phase5Route.NEEDS_CLARIFICATION,
            Phase5Route.UNSUPPORTED,
        }:
            raise ValueError("query_plan_ids must be non-empty for executable routes")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["route"] = self.route.value
        return payload


@dataclass(frozen=True)
class UnifiedCitation:
    """Common display citation for Commit, PR, Issue, Review, CI, and Revert."""

    citation_id: str
    source_id: str
    artifact_kind: str
    title: str
    occurred_at: str | None
    source_url: str
    excerpt: str

    def __post_init__(self) -> None:
        for field_name in ("citation_id", "source_id", "artifact_kind", "title", "source_url"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be non-empty")

    def to_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class ChatSessionState:
    """Conversation target and evidence state retained between turns."""

    session_id: str
    repository: str
    target: ChatTarget
    head_sha: str | None
    evidence_pack_id: str
    index_version: str
    updated_at: str

    def __post_init__(self) -> None:
        for field_name in ("session_id", "repository", "evidence_pack_id", "index_version", "updated_at"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be non-empty")
        self.target.validate()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class SessionFreshness:
    """Whether stored chat context can be reused safely."""

    can_reuse: bool
    reason: str
    stale_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "stale_fields", tuple(self.stale_fields))


def route_phase5_query(raw_input: str) -> UnifiedQueryPlan:
    """Route a user question to one or more Phase5 query plans."""

    interpreted = interpret_input(raw_input)
    return route_interpreted_phase5_query(interpreted)


def route_interpreted_phase5_query(interpreted: InterpretedInput) -> UnifiedQueryPlan:
    """Route already interpreted input without re-parsing it."""

    if interpreted.intent is QueryIntent.UNSUPPORTED:
        return UnifiedQueryPlan(
            route=Phase5Route.UNSUPPORTED,
            query_plan_ids=(),
            requires_current_change=False,
            reason="The input is outside the supported Git Archaeologist query contract.",
        )
    if not interpreted.can_resolve_target:
        return UnifiedQueryPlan(
            route=Phase5Route.NEEDS_CLARIFICATION,
            query_plan_ids=(),
            requires_current_change=False,
            reason=interpreted.clarification_reason or "A concrete repository target is required.",
        )

    question = (interpreted.question or "").lower()
    plan_ids: list[str] = []
    if _mentions_lineage(question):
        plan_ids.append("lineage-origin-maintenance")
    if _mentions_incident(question):
        plan_ids.append("incident-causal-history")
    if interpreted.intent is QueryIntent.CHANGE_RISK or _mentions_risk(question):
        plan_ids.append("historical-change-risk")
    if interpreted.intent is QueryIntent.IMPLEMENTATION_RATIONALE or not plan_ids:
        plan_ids.append("implementation-rationale")

    route = _route_for_plan_ids(tuple(plan_ids))
    return UnifiedQueryPlan(
        route=route,
        query_plan_ids=tuple(dict.fromkeys(plan_ids)),
        requires_current_change=interpreted.pr_url is not None or "historical-change-risk" in plan_ids,
        reason="Question routed by target grain, incident/risk keywords, and MVP intent.",
    )


def build_unified_citations(evidence_pack: ChatEvidencePack) -> tuple[UnifiedCitation, ...]:
    """Create stable citation rows from the chat Evidence Pack display view."""

    citations: list[UnifiedCitation] = []
    for index, item in enumerate(evidence_pack.items, start=1):
        citations.append(
            UnifiedCitation(
                citation_id=f"C{index}",
                source_id=item.source_id,
                artifact_kind=_artifact_kind_from_source_id(item.source_id),
                title=item.parent_event_id,
                occurred_at=None,
                source_url=item.source_url,
                excerpt=item.text,
            )
        )
    return tuple(citations)


def check_session_freshness(
    session: ChatSessionState,
    *,
    current_index_version: str,
    current_head_sha: str | None,
) -> SessionFreshness:
    """Prevent stale Evidence Packs from being treated as current answers."""

    stale_fields: list[str] = []
    if session.index_version != current_index_version:
        stale_fields.append("index_version")
    if session.head_sha != current_head_sha:
        stale_fields.append("head_sha")
    if stale_fields:
        return SessionFreshness(
            can_reuse=False,
            reason="Stored chat context is stale; rerun target resolution and evidence retrieval.",
            stale_fields=tuple(stale_fields),
        )
    return SessionFreshness(can_reuse=True, reason="Stored chat context matches the current repository state.")


def _route_for_plan_ids(plan_ids: tuple[str, ...]) -> Phase5Route:
    unique = tuple(dict.fromkeys(plan_ids))
    if len(unique) > 1:
        return Phase5Route.COMBINED
    if unique == ("lineage-origin-maintenance",):
        return Phase5Route.LINEAGE_ANALYSIS
    if unique == ("incident-causal-history",):
        return Phase5Route.INCIDENT_ANALYSIS
    if unique == ("historical-change-risk",):
        return Phase5Route.CHANGE_RISK
    return Phase5Route.IMPLEMENTATION_RATIONALE


def _mentions_lineage(question: str) -> bool:
    return _contains_any(question, ("line", "branch", "condition", "origin", "blame", "行", "条件", "起源", "維持"))


def _mentions_incident(question: str) -> bool:
    return _contains_any(question, ("incident", "ci", "failure", "revert", "bug", "障害", "失敗", "復旧", "revert"))


def _mentions_risk(question: str) -> bool:
    return _contains_any(question, ("risk", "regression", "compatibility", "danger", "リスク", "互換", "危険", "衝突"))


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _artifact_kind_from_source_id(source_id: str) -> str:
    prefix = source_id.split("-", 1)[0].lower()
    return {
        "commit": "commit",
        "pr": "pull_request",
        "pull": "pull_request",
        "issue": "issue",
        "review": "review",
        "ci": "ci",
        "revert": "revert",
    }.get(prefix, "evidence")
