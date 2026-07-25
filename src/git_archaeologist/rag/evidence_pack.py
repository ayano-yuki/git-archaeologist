"""Evidence Pack schema and token-budget selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Mapping


EVIDENCE_PACK_SCHEMA_VERSION = 1


class EvidenceStrength(StrEnum):
    """How directly an item supports an answer."""

    DIRECT = "direct"
    RELATED = "related"
    WEAK = "weak"


@dataclass(frozen=True)
class TargetCodeContext:
    """Code target that the Evidence Pack is about."""

    file_path: str
    symbol_id: str | None = None
    qualified_name: str | None = None
    commit_sha: str | None = None
    snippet: str | None = None

    def validate(self) -> None:
        if not self.file_path:
            raise EvidencePackViolation("target file_path must be non-empty")


@dataclass(frozen=True)
class EvidenceItem:
    """One citation-ready evidence item."""

    source_id: str
    parent_event_id: str
    source_url: str
    artifact_kind: str
    text: str
    token_count: int
    strength: EvidenceStrength
    occurred_at: datetime | None = None
    diff: str | None = None
    file_path: str | None = None
    symbol_id: str | None = None
    route: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "route", tuple(self.route))
        self.validate()

    def validate(self) -> None:
        for field_name in ("source_id", "parent_event_id", "source_url", "artifact_kind", "text"):
            if not getattr(self, field_name):
                raise EvidencePackViolation(f"{field_name} must be non-empty")
        if not self.source_url.startswith(("https://", "http://")):
            raise EvidencePackViolation("source_url must be an http or https URL")
        if self.token_count < 1:
            raise EvidencePackViolation("token_count must be positive")

    def priority_score(self) -> tuple[int, int]:
        strength_rank = {
            EvidenceStrength.DIRECT: 3,
            EvidenceStrength.RELATED: 2,
            EvidenceStrength.WEAK: 1,
        }[self.strength]
        return (strength_rank, -self.token_count)

    def to_dict(self) -> dict[str, object]:
        self.validate()
        payload = asdict(self)
        payload["strength"] = self.strength.value
        payload["occurred_at"] = self.occurred_at.isoformat() if self.occurred_at else None
        payload["route"] = list(self.route)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class OmittedEvidence:
    """Evidence excluded by the token budget."""

    source_id: str
    reason: str
    token_count: int


@dataclass(frozen=True)
class EvidencePack:
    """Reproducible payload passed to answer generation."""

    question: str
    target: TargetCodeContext
    items: tuple[EvidenceItem, ...]
    omitted: tuple[OmittedEvidence, ...]
    token_budget: int
    total_tokens: int
    pack_id: str
    schema_version: int = EVIDENCE_PACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "omitted", tuple(self.omitted))
        self.validate()

    def validate(self) -> None:
        if self.schema_version != EVIDENCE_PACK_SCHEMA_VERSION:
            raise EvidencePackViolation("unsupported evidence pack schema_version")
        if not self.question:
            raise EvidencePackViolation("question must be non-empty")
        if self.token_budget < 1:
            raise EvidencePackViolation("token_budget must be positive")
        if self.total_tokens > self.token_budget:
            raise EvidencePackViolation("total_tokens cannot exceed token_budget")
        self.target.validate()
        source_ids = set()
        for item in self.items:
            item.validate()
            if item.source_id in source_ids:
                raise EvidencePackViolation(f"duplicate source_id: {item.source_id}")
            source_ids.add(item.source_id)

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "pack_id": self.pack_id,
            "question": self.question,
            "target": asdict(self.target),
            "items": [item.to_dict() for item in self.items],
            "omitted": [asdict(item) for item in self.omitted],
            "token_budget": self.token_budget,
            "total_tokens": self.total_tokens,
        }


class EvidencePackViolation(ValueError):
    """Raised when evidence cannot be safely passed to generation."""


def build_evidence_pack(
    *,
    question: str,
    target: TargetCodeContext,
    candidate_items: tuple[EvidenceItem, ...],
    token_budget: int,
) -> EvidencePack:
    """Build an Evidence Pack by priority while respecting the token budget."""

    selected: list[EvidenceItem] = []
    omitted: list[OmittedEvidence] = []
    total_tokens = 0

    for item in sorted(candidate_items, key=lambda candidate: candidate.priority_score(), reverse=True):
        if total_tokens + item.token_count <= token_budget:
            selected.append(item)
            total_tokens += item.token_count
        else:
            omitted.append(
                OmittedEvidence(
                    source_id=item.source_id,
                    reason="token budget exhausted before this item",
                    token_count=item.token_count,
                )
            )

    pack = EvidencePack(
        question=question,
        target=target,
        items=tuple(selected),
        omitted=tuple(omitted),
        token_budget=token_budget,
        total_tokens=total_tokens,
        pack_id=_pack_id(question, target, tuple(selected), token_budget),
    )
    return pack


def estimate_token_count(text: str) -> int:
    """Small deterministic estimator used before tokenizer integration."""

    return max(1, len(text.split()))


def _pack_id(
    question: str,
    target: TargetCodeContext,
    selected: tuple[EvidenceItem, ...],
    token_budget: int,
) -> str:
    digest = sha256(
        "\0".join(
            (
                question,
                target.file_path,
                target.symbol_id or "",
                target.commit_sha or "",
                str(token_budget),
                *[item.source_id for item in selected],
            )
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"evidence-pack-{digest}"
