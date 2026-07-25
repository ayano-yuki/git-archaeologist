from __future__ import annotations

from datetime import datetime, timezone
import unittest

from git_archaeologist.evidence_reranker import (
    EvidenceCandidate,
    RerankDecisionKind,
    baseline_order,
    rerank_evidence,
)


class EvidenceRerankerTests(unittest.TestCase):
    def test_stub_relevance_can_promote_directly_relevant_review(self) -> None:
        result = rerank_evidence(
            "why hydration warning was delayed",
            (
                _candidate("commit", "Touched the same file", 0.9, "commit", relationship_strength=0.2),
                _candidate("review", "Review explains hydration warning delay", 0.4, "review", relationship_strength=0.9),
            ),
        )

        self.assertEqual("review", result.selected[0].candidate.candidate_id)
        self.assertLess(result.selected[0].original_rank, 3)
        self.assertIn("relevance=", result.selected[0].reasons[1])

    def test_symbol_match_and_recency_are_recorded_as_reasons(self) -> None:
        result = rerank_evidence(
            "createRoot risk",
            (
                _candidate(
                    "pr",
                    "createRoot risk was reviewed",
                    0.5,
                    "pull_request",
                    symbol_id="symbol-createRoot",
                    occurred_at=datetime(2024, 1, 25, tzinfo=timezone.utc),
                    relationship_strength=0.8,
                ),
            ),
            target_symbol_id="symbol-createRoot",
            now=datetime(2024, 2, 1, tzinfo=timezone.utc),
        )

        reasons = " ".join(result.selected[0].reasons)
        self.assertIn("matched target symbol", reasons)
        self.assertIn("recency=", reasons)

    def test_low_score_candidates_are_excluded_with_reason(self) -> None:
        result = rerank_evidence(
            "scheduler",
            (_candidate("unrelated", "package metadata", 0.1, "issue"),),
            min_score=0.2,
        )

        self.assertEqual((), result.selected)
        self.assertEqual(RerankDecisionKind.EXCLUDED, result.excluded[0].decision)
        self.assertIn("minimum score", result.excluded[0].reasons[-1])

    def test_baseline_order_is_available_for_comparison(self) -> None:
        candidates = (
            _candidate("low", "direct answer", 0.1, "review"),
            _candidate("high", "same file", 0.9, "commit"),
        )

        self.assertEqual(("high", "low"), baseline_order(candidates))
        self.assertEqual("low", rerank_evidence("direct answer", candidates).selected[0].candidate.candidate_id)


def _candidate(
    candidate_id: str,
    text: str,
    base_score: float,
    artifact_kind: str,
    *,
    symbol_id: str | None = None,
    occurred_at: datetime | None = None,
    relationship_strength: float = 0.0,
) -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=candidate_id,
        text=text,
        base_score=base_score,
        artifact_kind=artifact_kind,
        source_url=f"https://github.com/facebook/react/{candidate_id}",
        symbol_id=symbol_id,
        occurred_at=occurred_at,
        relationship_strength=relationship_strength,
    )


if __name__ == "__main__":
    unittest.main()
