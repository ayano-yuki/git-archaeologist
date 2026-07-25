"""Local Phase2 smoke check that exercises stabilization primitives."""

from __future__ import annotations

import json

from git_archaeologist.demo_chat import run_demo_chat
from git_archaeologist.evaluation.evaluation_harness import (
    AnswerEvaluation,
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
    ensure_answer_uses_published_index,
)
from git_archaeologist.evaluation.quality_analysis import (
    ExperimentRun,
    build_failure_taxonomy,
    compare_ablation,
    decide_sft_need,
)
from git_archaeologist.ops.query_trace import InMemoryQueryTraceStore
from git_archaeologist.ops.resilience import FailureKind, decide_fallback
from git_archaeologist.ops.versioned_cache import CacheKey, CacheOperation, VersionedCache


def run_phase2_smoke() -> dict[str, object]:
    """Run a deterministic end-to-end Phase2 readiness check."""

    old_state = SyncState(
        repository_id="react/react",
        index_version="index-v1",
        synced_at="2026-01-01T00:00:00Z",
        watermarks=(
            SyncWatermark(ArtifactSyncKind.PULL_REQUEST, "2026-01-01T00:00:00Z", head_sha="old-sha"),
        ),
    )
    update = ArtifactUpdate(
        ArtifactSyncKind.PULL_REQUEST,
        "pr-12345",
        "2026-01-02T00:00:00Z",
        head_sha="new-sha",
    )
    sync_plan = plan_incremental_sync(old_state, (update,))
    new_state = apply_sync_success(
        old_state,
        sync_plan.updates,
        new_index_version="index-v2",
        synced_at="2026-01-02T00:00:00Z",
    )

    generation = IndexGeneration("index-v2", "index-v2", "index-v2", "index-v2", new_state.synced_at)
    transaction = IndexTransaction(base_index_version="index-v1", staged_index_version="index-v2").publish(generation)
    answer_index = ensure_answer_uses_published_index(generation, transaction)

    cache: VersionedCache[str] = VersionedCache()
    stale_key = CacheKey.build(
        operation=CacheOperation.EVIDENCE_PACK,
        target="react/react#12345",
        index_version="index-v1",
        model_version="demo-model-v1",
    )
    fresh_key = CacheKey.build(
        operation=CacheOperation.EVIDENCE_PACK,
        target="react/react#12345",
        index_version=answer_index.index_version,
        model_version="demo-model-v1",
    )
    cache.put(stale_key, "old-pack")
    invalidated = cache.invalidate_index_version("index-v1")
    cache.put(fresh_key, "fresh-pack")

    trace_store = InMemoryQueryTraceStore()
    chat_result = run_demo_chat(trace_store=trace_store, model_version="demo-model-v1")

    report = build_evaluation_report(
        target_cases=(
            TargetResolutionEvaluation("case-target-ok", "target-1", "target-1"),
        ),
        retrieval_cases=(
            RetrievalEvaluation("case-search-ok", ("source-1",), ("source-1",)),
        ),
        answer_cases=(
            AnswerEvaluation("case-answer-ok", "risk_found", "risk_found", False, False, 0, 0),
        ),
    )
    taxonomy = build_failure_taxonomy(report)
    ablation = compare_ablation(
        ExperimentRun("baseline", "baseline", {"evidence_recall_at_k": 1.0, "citation_consistency_rate": 1.0}),
        (
            ExperimentRun(
                "graph-expansion-window",
                "graph_expansion",
                {"evidence_recall_at_k": 1.0, "citation_consistency_rate": 1.0},
            ),
        ),
    )
    sft_decision = decide_sft_need(report, taxonomy)
    fallback = decide_fallback(FailureKind.PARTIAL_FETCH)

    passed = (
        len(sync_plan.updates) == 1
        and new_state.index_version == "index-v2"
        and answer_index.index_version == "index-v2"
        and invalidated == 1
        and cache.get(fresh_key) == "fresh-pack"
        and chat_result.status.value == "answered"
        and len(trace_store.all()) == 1
        and sft_decision.decision == "defer_sft"
        and fallback.can_use_partial_evidence
    )
    return {
        "status": "phase2_smoke_passed" if passed else "phase2_smoke_failed",
        "sync_updates": len(sync_plan.updates),
        "index_version": answer_index.index_version,
        "cache_hit_rate": cache.stats.hit_rate,
        "trace_count": len(trace_store.all()),
        "chat_status": chat_result.status.value,
        "failure_patterns": taxonomy.to_dict(),
        "ablation": [result.__dict__ for result in ablation],
        "sft_decision": sft_decision.to_dict(),
        "partial_fetch_message": fallback.user_message,
    }


def main() -> None:
    print(json.dumps(run_phase2_smoke(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
