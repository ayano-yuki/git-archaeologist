"""Deterministic MVP input interpreter.

This module turns raw chat text into the structured request shape used by the
Target Resolver. It intentionally handles only deterministic routing and does
not ask an LLM to guess missing targets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from git_archaeologist.evaluation.mvp_contracts import (
    InputDecision,
    MvpInputKind,
    StructuredMvpInput,
    structure_mvp_input,
)


class QueryIntent(StrEnum):
    """Supported MVP question intents."""

    IMPLEMENTATION_RATIONALE = "implementation_rationale"
    CHANGE_RISK = "change_risk"
    TARGET_UNKNOWN = "target_unknown"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class InterpretedInput:
    """Structured input with a deterministic intent label."""

    decision: InputDecision
    intent: QueryIntent
    kind: MvpInputKind | None
    question: str | None = None
    pr_url: str | None = None
    repository: str | None = None
    pull_request_number: int | None = None
    file_path: str | None = None
    symbol_name: str | None = None
    code_snippet: str | None = None
    clarification_reason: str | None = None

    @property
    def can_resolve_target(self) -> bool:
        return self.decision == InputDecision.TARGET_RESOLVED

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["decision"] = self.decision.value
        payload["intent"] = self.intent.value
        payload["kind"] = self.kind.value if self.kind else None
        return {key: value for key, value in payload.items() if value is not None}


def interpret_input(raw_input: str) -> InterpretedInput:
    """Interpret raw chat text into the MVP structured query contract."""

    structured = structure_mvp_input(raw_input)
    intent = classify_intent(structured)
    return _with_intent(structured, intent)


def classify_intent(structured: StructuredMvpInput) -> QueryIntent:
    """Classify rationale, risk, target-unknown, and unsupported requests."""

    if structured.decision == InputDecision.UNSUPPORTED:
        return QueryIntent.UNSUPPORTED
    if structured.decision == InputDecision.NEEDS_CLARIFICATION:
        return QueryIntent.TARGET_UNKNOWN

    question = (structured.question or "").lower()
    if _contains_any(
        question,
        (
            "risk",
            "risky",
            "regression",
            "compatibility",
            "conflict",
            "break",
            "danger",
            "リスク",
            "危険",
            "互換",
            "壊",
            "衝突",
        ),
    ):
        return QueryIntent.CHANGE_RISK
    if _contains_any(
        question,
        (
            "why",
            "reason",
            "rationale",
            "explain",
            "history",
            "なぜ",
            "理由",
            "経緯",
            "説明",
        ),
    ):
        return QueryIntent.IMPLEMENTATION_RATIONALE
    return QueryIntent.TARGET_UNKNOWN


def _with_intent(structured: StructuredMvpInput, intent: QueryIntent) -> InterpretedInput:
    return InterpretedInput(
        decision=structured.decision,
        intent=intent,
        kind=structured.kind,
        question=structured.question,
        pr_url=structured.pr_url,
        repository=structured.repository,
        pull_request_number=structured.pull_request_number,
        file_path=structured.file_path,
        symbol_name=structured.symbol_name,
        code_snippet=structured.code_snippet,
        clarification_reason=structured.clarification_reason,
    )


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
