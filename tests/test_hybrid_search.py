from __future__ import annotations

from datetime import datetime, timezone
import unittest

from git_archaeologist.search.hybrid_search import (
    HybridSearchEngine,
    KeywordSearchEngine,
    SearchDocument,
    SearchFilter,
    SearchSource,
    DeterministicVectorSearchBackend,
    reciprocal_rank_fusion,
)


class HybridSearchTests(unittest.TestCase):
    def test_keyword_search_finds_exact_identifiers(self) -> None:
        engine = KeywordSearchEngine(
            (
                _document("commit-1", "Fix createRoot hydration warning", file_path="packages/react-dom/client.js"),
                _document("commit-2", "Refactor scheduler lanes", file_path="packages/scheduler/src/index.js"),
            )
        )

        hits = engine.search("createRoot packages/react-dom/client.js")

        self.assertEqual("commit-1", hits[0].document.document_id)
        self.assertEqual(SearchSource.KEYWORD, hits[0].source)
        self.assertIn("createroot", hits[0].matched_terms)

    def test_vector_backend_returns_natural_language_candidates(self) -> None:
        documents = (
            _document("review-1", "This review explains why hydration warnings are delayed."),
            _document("issue-2", "Unrelated issue about package metadata."),
        )
        backend = DeterministicVectorSearchBackend({"review-1": 0.89, "issue-2": 0.12})

        hits = backend.search("why did we delay hydration warning?", documents)

        self.assertEqual(["review-1", "issue-2"], [hit.document.document_id for hit in hits])
        self.assertIn("deterministic vector score", hits[0].explanation)

    def test_rank_fusion_preserves_source_explanations(self) -> None:
        documents = (
            _document("a", "exact text"),
            _document("b", "semantic text"),
        )
        keyword = KeywordSearchEngine(documents).search("exact")
        vector = DeterministicVectorSearchBackend({"b": 0.99, "a": 0.75}).search("semantic exact", documents)

        hits = reciprocal_rank_fusion(keyword, vector)

        self.assertEqual(SearchSource.FUSION, hits[0].source)
        self.assertTrue(any("keyword rank" in hit.explanation or "vector rank" in hit.explanation for hit in hits))

    def test_filters_apply_to_keyword_and_vector_results(self) -> None:
        documents = (
            _document(
                "old",
                "createRoot warning",
                file_path="packages/react-dom/client.js",
                artifact_kind="review",
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            ),
            _document(
                "new",
                "createRoot warning",
                file_path="packages/react-dom/client.js",
                artifact_kind="issue",
                timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
            ),
        )
        engine = HybridSearchEngine(documents, DeterministicVectorSearchBackend({"old": 0.5, "new": 0.9}))

        hits = engine.search(
            "createRoot warning",
            search_filter=SearchFilter(
                artifact_kind="issue",
                start_time=datetime(2024, 5, 1, tzinfo=timezone.utc),
            ),
        )

        self.assertEqual(["new"], [hit.document.document_id for hit in hits])
        self.assertIn("keyword rank", hits[0].explanation)
        self.assertIn("vector rank", hits[0].explanation)


def _document(
    document_id: str,
    text: str,
    *,
    file_path: str | None = None,
    artifact_kind: str | None = None,
    timestamp: datetime | None = None,
) -> SearchDocument:
    return SearchDocument(
        document_id=document_id,
        text=text,
        file_path=file_path,
        artifact_kind=artifact_kind,
        timestamp=timestamp,
    )


if __name__ == "__main__":
    unittest.main()
