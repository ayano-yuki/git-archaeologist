from __future__ import annotations

import unittest

from git_archaeologist.demo_chat import run_demo_chat
from git_archaeologist.evaluation.evaluation_harness import (
    AnswerEvaluation,
    FailureStage,
    RetrievalEvaluation,
    TargetResolutionEvaluation,
    build_evaluation_report,
)
from git_archaeologist.ops.incremental_sync import (
    ArtifactSyncKind,
    ArtifactUpdate,
    SyncState,
    SyncWatermark,
    apply_sync_success,
    plan_incremental_sync,
)
from git_archaeologist.ops.index_integrity import (
    IndexGeneration,
    IndexTransaction,
    IndexTransactionStatus,
    ensure_answer_uses_published_index,
)
from git_archaeologist.ops.smoke import run_stability_smoke
from git_archaeologist.evaluation.quality_analysis import (
    ExperimentRun,
    FailureResponsibility,
    build_failure_taxonomy,
    compare_ablation,
    decide_sft_need,
)
from git_archaeologist.ops.query_trace import InMemoryQueryTraceStore
from git_archaeologist.ops.resilience import FailureKind, classify_failure_message, decide_fallback
from git_archaeologist.ops.versioned_cache import CacheKey, CacheOperation, VersionedCache


class StabilityTests(unittest.TestCase):
    def test_incremental_sync_selects_changed_only_and_tracks_tombstone(self) -> None:
        state = SyncState(
            repository_id="react/react",
            index_version="index-v1",
            synced_at="2026-01-01T00:00:00Z",
            watermarks=(SyncWatermark(ArtifactSyncKind.PULL_REQUEST, "2026-01-02T00:00:00Z", head_sha="sha-1"),),
        )
        unchanged = ArtifactUpdate(
            ArtifactSyncKind.PULL_REQUEST,
            "pr-1",
            "2026-01-01T12:00:00Z",
            head_sha="sha-1",
        )
        force_pushed = ArtifactUpdate(
            ArtifactSyncKind.PULL_REQUEST,
            "pr-2",
            "2026-01-01T12:00:00Z",
            head_sha="sha-2",
        )
        deleted = ArtifactUpdate(ArtifactSyncKind.ISSUE, "issue-1", "2026-01-03T00:00:00Z", deleted=True)

        plan = plan_incremental_sync(state, (unchanged, force_pushed, deleted))
        new_state = apply_sync_success(
            state,
            plan.updates,
            new_index_version="index-v2",
            synced_at="2026-01-03T00:00:00Z",
        )

        self.assertEqual(("pr-2", "issue-1"), tuple(update.artifact_id for update in plan.updates))
        self.assertEqual(("pr-1",), plan.skipped_artifact_ids)
        self.assertEqual("index-v2", new_state.index_version)
        self.assertIn("issue-1", new_state.tombstones)

    def test_index_transaction_only_publishes_consistent_generation(self) -> None:
        generation = IndexGeneration("index-v2", "index-v2", "index-v2", "index-v2", "2026-01-02T00:00:00Z")
        transaction = IndexTransaction("index-v1", "index-v2").publish(generation)
        answer_index = ensure_answer_uses_published_index(generation, transaction)

        self.assertEqual(IndexTransactionStatus.PUBLISHED, transaction.status)
        self.assertEqual("index-v2", answer_index.index_version)

        broken = IndexGeneration("index-v2", "index-v1", "index-v2", "index-v2", "2026-01-02T00:00:00Z")
        with self.assertRaises(ValueError):
            IndexTransaction("index-v1", "index-v2").publish(broken)

    def test_query_trace_records_input_to_final_answer(self) -> None:
        store = InMemoryQueryTraceStore()
        result = run_demo_chat(trace_store=store, model_version="demo-model-v1")
        trace = store.get(result.trace_id)

        self.assertEqual("answered", trace.result_status)
        self.assertEqual(
            (
                "input_interpretation",
                "current_change_context",
                "target_resolution",
                "evidence_retrieval",
                "answer_generation",
                "citation_verification",
            ),
            tuple(step.name for step in trace.steps),
        )
        self.assertEqual("demo-model-v1", trace.model_version)

    def test_failure_fallback_does_not_mask_partial_fetch_as_normal_answer(self) -> None:
        kind = classify_failure_message("partial fetch interrupted after page 2")
        decision = decide_fallback(kind)

        self.assertEqual(FailureKind.PARTIAL_FETCH, decision.failure_kind)
        self.assertTrue(decision.can_use_partial_evidence)
        self.assertIn("一部", decision.user_message)

    def test_versioned_cache_invalidates_old_index_entries(self) -> None:
        cache: VersionedCache[str] = VersionedCache()
        old_key = CacheKey.build(
            operation=CacheOperation.SEARCH,
            target="ReactDOMRoot",
            index_version="index-v1",
            model_version="embed-v1",
        )
        new_key = CacheKey.build(
            operation=CacheOperation.SEARCH,
            target="ReactDOMRoot",
            index_version="index-v2",
            model_version="embed-v1",
        )

        cache.put(old_key, "old")
        cache.put(new_key, "new")
        self.assertEqual(1, cache.invalidate_index_version("index-v1"))

        self.assertIsNone(cache.get(old_key))
        self.assertEqual("new", cache.get(new_key))
        self.assertEqual(0.5, cache.stats.hit_rate)

    def test_failure_taxonomy_ablation_and_sft_decision_are_metric_backed(self) -> None:
        report = build_evaluation_report(
            target_cases=(TargetResolutionEvaluation("case-target", "target-1", "target-2"),),
            retrieval_cases=(RetrievalEvaluation("case-search", ("source-1",), ("other",)),),
            answer_cases=(AnswerEvaluation("case-answer", "risk_found", "risk_found", False, False, 1, 0),),
        )
        taxonomy = build_failure_taxonomy(report)
        ablations = compare_ablation(
            ExperimentRun("baseline", "baseline", {"evidence_recall_at_k": 0.4}),
            (ExperimentRun("chunk-size", "chunking", {"evidence_recall_at_k": 0.6}),),
        )
        decision = decide_sft_need(report, taxonomy)

        self.assertIn(FailureStage.TARGET_RESOLUTION, {pattern.stage for pattern in taxonomy.patterns})
        self.assertIn(FailureResponsibility.SEARCH, {pattern.responsibility for pattern in taxonomy.patterns})
        self.assertEqual("improved", ablations[0].verdict)
        self.assertEqual("defer_sft", decision.decision)
        self.assertIn("RAG改善", " ".join(decision.reasons))

    def test_stability_smoke_passes(self) -> None:
        result = run_stability_smoke()

        self.assertEqual("stability_smoke_passed", result["status"])
        self.assertEqual("answered", result["chat_status"])
        self.assertEqual("defer_sft", result["sft_decision"]["decision"])


if __name__ == "__main__":
    unittest.main()
