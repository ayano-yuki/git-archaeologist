"""Evidence reranking with explicit features and decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re
from typing import Protocol


class RerankDecisionKind(StrEnum):
    """Whether a candidate was retained for the Evidence Pack."""

    SELECTED = "selected"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class EvidenceCandidate:
    """Candidate evidence before reranking."""

    candidate_id: str
    text: str
    base_score: float
    artifact_kind: str
    source_url: str
    symbol_id: str | None = None
    occurred_at: datetime | None = None
    relationship_strength: float = 0.0

    def validate(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id must be non-empty")
        if not self.text.strip():
            raise ValueError("text must be non-empty")
        if not self.source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be an http or https URL")


@dataclass(frozen=True)
class RerankFeatures:
    """Features used to explain the rerank score."""

    relevance: float
    symbol_match: float
    recency: float
    relationship_strength: float

    @property
    def weighted_score(self) -> float:
        return round(
            self.relevance * 0.55
            + self.symbol_match * 0.2
            + self.recency * 0.1
            + self.relationship_strength * 0.15,
            6,
        )


@dataclass(frozen=True)
class RerankDecision:
    """Rerank result with before/after rank and reasons."""

    candidate: EvidenceCandidate
    original_rank: int
    reranked_rank: int | None
    final_score: float
    decision: RerankDecisionKind
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))


@dataclass(frozen=True)
class RerankResult:
    """Selected and excluded candidates from one rerank run."""

    model_version: str
    selected: tuple[RerankDecision, ...]
    excluded: tuple[RerankDecision, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected", tuple(self.selected))
        object.__setattr__(self, "excluded", tuple(self.excluded))


class RelevanceBackend(Protocol):
    """Replaceable model or heuristic relevance scorer."""

    model_version: str

    def score(self, query: str, candidates: tuple[EvidenceCandidate, ...]) -> Mapping[str, float]:
        """Return relevance scores by candidate ID."""


@dataclass(frozen=True)
class LexicalRelevanceBackend:
    """Deterministic baseline relevance scorer."""

    model_version: str = "lexical-baseline-v1"

    def score(self, query: str, candidates: tuple[EvidenceCandidate, ...]) -> Mapping[str, float]:
        query_terms = _tokens(query)
        if not query_terms:
            return {candidate.candidate_id: 0.0 for candidate in candidates}
        return {
            candidate.candidate_id: len(query_terms & _tokens(candidate.text)) / len(query_terms)
            for candidate in candidates
        }


def rerank_evidence(
    query: str,
    candidates: tuple[EvidenceCandidate, ...],
    *,
    target_symbol_id: str | None = None,
    backend: RelevanceBackend | None = None,
    now: datetime | None = None,
    limit: int = 5,
    min_score: float = 0.05,
) -> RerankResult:
    """Rerank evidence while preserving baseline comparison and exclusion reasons."""

    scorer = backend or LexicalRelevanceBackend()
    for candidate in candidates:
        candidate.validate()

    relevance_by_id = scorer.score(query, candidates)
    scored: list[tuple[EvidenceCandidate, int, RerankFeatures]] = []
    for original_rank, candidate in enumerate(
        sorted(candidates, key=lambda item: item.base_score, reverse=True),
        start=1,
    ):
        features = RerankFeatures(
            relevance=round(relevance_by_id.get(candidate.candidate_id, 0.0), 6),
            symbol_match=1.0 if target_symbol_id and candidate.symbol_id == target_symbol_id else 0.0,
            recency=_recency_score(candidate, now),
            relationship_strength=max(0.0, min(candidate.relationship_strength, 1.0)),
        )
        scored.append((candidate, original_rank, features))

    ordered = sorted(scored, key=lambda item: (item[2].weighted_score, item[0].base_score), reverse=True)
    selected: list[RerankDecision] = []
    excluded: list[RerankDecision] = []
    for reranked_index, (candidate, original_rank, features) in enumerate(ordered, start=1):
        reasons = _reasons(candidate, features, original_rank, reranked_index)
        if reranked_index <= limit and features.weighted_score >= min_score:
            selected.append(
                RerankDecision(
                    candidate=candidate,
                    original_rank=original_rank,
                    reranked_rank=reranked_index,
                    final_score=features.weighted_score,
                    decision=RerankDecisionKind.SELECTED,
                    reasons=reasons,
                )
            )
        else:
            excluded.append(
                RerankDecision(
                    candidate=candidate,
                    original_rank=original_rank,
                    reranked_rank=None,
                    final_score=features.weighted_score,
                    decision=RerankDecisionKind.EXCLUDED,
                    reasons=(*reasons, "below limit or minimum score"),
                )
            )

    return RerankResult(model_version=scorer.model_version, selected=tuple(selected), excluded=tuple(excluded))


def baseline_order(candidates: tuple[EvidenceCandidate, ...]) -> tuple[str, ...]:
    """Return candidate IDs in pre-rerank score order."""

    return tuple(candidate.candidate_id for candidate in sorted(candidates, key=lambda item: item.base_score, reverse=True))


def _reasons(
    candidate: EvidenceCandidate,
    features: RerankFeatures,
    original_rank: int,
    reranked_rank: int,
) -> tuple[str, ...]:
    reasons = [
        f"baseline rank {original_rank} became rerank rank {reranked_rank}",
        f"relevance={features.relevance:.3f}",
        f"relationship_strength={features.relationship_strength:.3f}",
    ]
    if features.symbol_match:
        reasons.append(f"matched target symbol {candidate.symbol_id}")
    if features.recency:
        reasons.append(f"recency={features.recency:.3f}")
    return tuple(reasons)


def _recency_score(candidate: EvidenceCandidate, now: datetime | None) -> float:
    if candidate.occurred_at is None or now is None:
        return 0.0
    age_days = max((now - candidate.occurred_at).days, 0)
    return round(1 / (1 + age_days / 30), 6)


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9_]+", text)}
