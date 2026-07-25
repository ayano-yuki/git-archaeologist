from __future__ import annotations

from datetime import datetime, timezone
import unittest

from git_archaeologist.rag.multistage_search import (
    EventCandidate,
    MultiStageSearchResult,
    PlanStepKind,
    QueryTarget,
    RetrievalFilter,
    RetrievedCandidate,
    run_multistage_search,
)


class MultiStageSearchTests(unittest.TestCase):
    def test_records_symbol_commit_to_graph_to_search_route(self) -> None:
        result = run_multistage_search(
            "why was createRoot changed?",
            QueryTarget(symbol_id="symbol-createRoot", commit_shas=("abc1234",)),
            graph_backend=_GraphBackend(),
            search_backend=_SearchBackend(),
        )

        self.assertIsInstance(result, MultiStageSearchResult)
        self.assertEqual(
            [PlanStepKind.SYMBOL_COMMITS, PlanStepKind.GRAPH_EXPANSION, PlanStepKind.SEARCH_CANDIDATES],
            [step.step_kind for step in result.plan_steps],
        )
        self.assertEqual("candidate-pr-1", result.candidates[0].candidate_id)
        self.assertIn("commit-abc1234", result.candidates[0].route)
        self.assertIn("pr-1", result.candidates[0].route)

    def test_filters_by_time_and_target_scope(self) -> None:
        result = run_multistage_search(
            "createRoot warning",
            QueryTarget(symbol_id="symbol-createRoot", file_path="packages/react-dom/client.js", commit_shas=("abc1234",)),
            graph_backend=_GraphBackend(),
            search_backend=_SearchBackend(),
            retrieval_filter=RetrievalFilter(
                start_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                file_path="packages/react-dom/client.js",
            ),
        )

        filter_step = result.plan_steps[2]
        self.assertEqual(PlanStepKind.FILTER, filter_step.step_kind)
        self.assertNotIn("commit-abc1234", filter_step.output_ids)
        self.assertEqual(["candidate-pr-1"], [candidate.candidate_id for candidate in result.candidates])

    def test_empty_graph_still_produces_auditable_steps(self) -> None:
        result = run_multistage_search(
            "unknown",
            QueryTarget(commit_shas=("missing",)),
            graph_backend=_EmptyGraphBackend(),
            search_backend=_SearchBackend(),
        )

        self.assertEqual(3, len(result.plan_steps))
        self.assertEqual((), result.candidates)
        self.assertEqual((), result.plan_steps[-1].output_ids)


class _GraphBackend:
    def events_for_commits(self, commit_shas: tuple[str, ...]) -> tuple[EventCandidate, ...]:
        return tuple(
            EventCandidate(
                event_id=f"commit-{sha}",
                event_kind="commit",
                occurred_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                source_url=f"https://github.com/facebook/react/commit/{sha}",
                file_path="packages/react-dom/client.js",
                symbol_id="symbol-createRoot",
            )
            for sha in commit_shas
        )

    def expand(self, event_ids: tuple[str, ...]) -> tuple[EventCandidate, ...]:
        return (
            EventCandidate(
                event_id="pr-1",
                event_kind="pull_request",
                occurred_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
                source_url="https://github.com/facebook/react/pull/1",
                file_path="packages/react-dom/client.js",
                symbol_id="symbol-createRoot",
                related_event_ids=event_ids,
                relationship_strength=0.9,
            ),
            EventCandidate(
                event_id="issue-2",
                event_kind="issue",
                occurred_at=datetime(2024, 1, 4, tzinfo=timezone.utc),
                source_url="https://github.com/facebook/react/issues/2",
                file_path="packages/other.js",
                relationship_strength=0.4,
            ),
        )


class _EmptyGraphBackend:
    def events_for_commits(self, commit_shas: tuple[str, ...]) -> tuple[EventCandidate, ...]:
        return ()

    def expand(self, event_ids: tuple[str, ...]) -> tuple[EventCandidate, ...]:
        return ()


class _SearchBackend:
    def search(self, query: str, events: tuple[EventCandidate, ...]) -> tuple[RetrievedCandidate, ...]:
        return tuple(
            RetrievedCandidate(
                candidate_id=f"candidate-{event.event_id}",
                event=event,
                score=0.8 + event.relationship_strength,
                route=(*event.related_event_ids, event.event_id),
                reason=f"event matched query: {query}",
            )
            for event in events
            if event.event_kind == "pull_request"
        )


if __name__ == "__main__":
    unittest.main()
