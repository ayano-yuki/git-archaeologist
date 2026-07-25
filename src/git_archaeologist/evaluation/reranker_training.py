"""Small deterministic ranking-learning helpers for Evidence Reranker data."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceCandidate:
    """Evidence text with a stable training ID."""

    evidence_id: str
    text: str


@dataclass(frozen=True)
class RankingTrainingExample:
    """One query with a positive evidence item and hard negatives."""

    query: str
    positive: EvidenceCandidate
    hard_negatives: tuple[EvidenceCandidate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "hard_negatives", tuple(self.hard_negatives))
        if not self.hard_negatives:
            raise ValueError("hard_negatives must not be empty")


@dataclass(frozen=True)
class KeywordRerankerProfile:
    """Learned lexical weights for a simple local reranker baseline."""

    token_weights: dict[str, float]
    training_example_count: int


@dataclass(frozen=True)
class RerankerTrainingReport:
    """Ranking evaluation summary."""

    example_count: int
    mean_reciprocal_rank: float
    positive_first_count: int

    @property
    def passed(self) -> bool:
        return self.positive_first_count == self.example_count


def train_keyword_reranker_profile(examples: tuple[RankingTrainingExample, ...]) -> KeywordRerankerProfile:
    """Learn positive-minus-negative token weights from ranking examples."""

    if not examples:
        raise ValueError("training examples must not be empty")
    weights: dict[str, float] = {}
    for example in examples:
        query_tokens = _tokens(example.query)
        for token in _tokens(example.positive.text) & query_tokens:
            weights[token] = weights.get(token, 0.0) + 1.0
        for negative in example.hard_negatives:
            for token in _tokens(negative.text) & query_tokens:
                weights[token] = weights.get(token, 0.0) - 0.25
    return KeywordRerankerProfile(token_weights=weights, training_example_count=len(examples))


def evaluate_keyword_reranker(
    profile: KeywordRerankerProfile,
    examples: tuple[RankingTrainingExample, ...],
) -> RerankerTrainingReport:
    """Evaluate whether positives outrank hard negatives."""

    reciprocal_ranks: list[float] = []
    positive_first_count = 0
    for example in examples:
        candidates = (example.positive,) + example.hard_negatives
        ranked = sorted(
            candidates,
            key=lambda candidate: _score(profile, example.query, candidate.text),
            reverse=True,
        )
        positive_rank = next(
            rank for rank, candidate in enumerate(ranked, start=1) if candidate.evidence_id == example.positive.evidence_id
        )
        reciprocal_ranks.append(1 / positive_rank)
        if positive_rank == 1:
            positive_first_count += 1
    return RerankerTrainingReport(
        example_count=len(examples),
        mean_reciprocal_rank=sum(reciprocal_ranks) / len(reciprocal_ranks),
        positive_first_count=positive_first_count,
    )


def _score(profile: KeywordRerankerProfile, query: str, text: str) -> float:
    query_tokens = _tokens(query)
    return sum(profile.token_weights.get(token, 0.0) for token in _tokens(text) & query_tokens)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))
