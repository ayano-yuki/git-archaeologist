"""Local smoke checks for stabilization, incidents, and lineage."""

from __future__ import annotations

import json

from git_archaeologist.demo_chat import run_demo_chat
from git_archaeologist.evaluation.evaluation_harness import (
    AnswerEvaluation,
    RetrievalEvaluation,
    TargetResolutionEvaluation,
    build_evaluation_report,
)
from git_archaeologist.normalization.ci_failures import (
    generate_failure_signature,
    parse_ci_failure_event,
)
from git_archaeologist.normalization.incident_graph import (
    ConstraintState,
    IncidentNode,
    RevertState,
    build_incident_graph,
    detect_revert_state,
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
from git_archaeologist.rag.incident_answering import (
    build_incident_answer,
    evaluate_historical_risk,
)
from git_archaeologist.rag.lineage_answering import build_lineage_answer
from git_archaeologist.search.lineage_analysis import (
    LineageRelationKind,
    build_condition_history_entry,
    detect_file_lineage,
    detect_symbol_lineage,
    parse_blame_porcelain,
    separate_rationale,
)


def run_stability_smoke() -> dict[str, object]:
    """Run a deterministic end-to-end stabilization readiness check."""

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
        "status": "stability_smoke_passed" if passed else "stability_smoke_failed",
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


def run_incident_smoke() -> dict[str, object]:
    """Exercise CI parsing, signatures, incident graph, answers, and risk."""

    failure = parse_ci_failure_event(
        repository_id="react/react",
        workflow_name="CI",
        job_name="unit",
        step_name="test",
        head_sha="abc1234",
        occurred_at="2026-01-02T00:00:00Z",
        source_url="https://github.com/react/react/actions/runs/1",
        log_text=(
            "FAIL ReactDOM.createRoot.test\n"
            "AssertionError: expected guard to preserve fallback 42\n"
            "packages/react-dom/client.js:120\n"
            "token=super-secret\n"
        ),
    )
    signature = generate_failure_signature(failure)
    revert = detect_revert_state(
        'Revert "Add createRoot guard"\n\nThis reverts commit abc1234',
        patch_reverse_similarity=0.92,
    )
    graph = build_incident_graph(
        incident_id="incident-create-root-guard",
        introducing_change=IncidentNode(
            "commit-abc1234",
            "change",
            "2026-01-01T00:00:00Z",
            "Add createRoot guard",
            "packages/react-dom/client.js",
            "ReactDOM.createRoot",
            "https://github.com/react/react/commit/abc1234",
        ),
        failure=IncidentNode(
            signature.signature_id,
            "ci_failure",
            failure.occurred_at,
            failure.message,
            "packages/react-dom/client.js",
            "ReactDOM.createRoot",
            failure.source_url,
        ),
        fix=IncidentNode(
            "commit-fix",
            "fix",
            "2026-01-03T00:00:00Z",
            "Preserve fallback path",
            "packages/react-dom/client.js",
            "ReactDOM.createRoot",
            "https://github.com/react/react/commit/fix",
        ),
    )
    answer = build_incident_answer(graph)
    risk = evaluate_historical_risk(
        changed_files=("packages/react-dom/client.js",),
        changed_symbols=("ReactDOM.createRoot",),
        failure_signature_ids=(),
        incident_graphs=(graph,),
    )
    passed = (
        "<redacted>" in failure.redacted_excerpt
        and failure.test_name == "ReactDOM.createRoot.test"
        and signature.primary_stack_frame == "packages/react-dom/client.js:<line>"
        and revert.state is RevertState.REVERTED
        and graph.constraint_state is ConstraintState.MAINTAINED
        and answer.observed_cause is not None
        and risk.risk_found
    )
    return {
        "status": "incident_smoke_passed" if passed else "incident_smoke_failed",
        "ci_failure": failure.to_dict(),
        "signature": signature.to_dict(),
        "revert": revert.to_dict(),
        "incident_graph": graph.to_dict(),
        "answer": answer.to_dict(),
        "historical_risk": risk.to_dict(),
    }


def run_lineage_smoke() -> dict[str, object]:
    """Exercise blame parsing, lineage, condition history, and answers."""

    blame = (
        "abc1234 10 20 1\n"
        "author Example\n"
        "\tif (supportsFallback && hasContainer) {\n"
    )
    candidates = parse_blame_porcelain(
        blame,
        file_path="packages/react-dom/client.js",
        requested_start=20,
        requested_end=20,
    )
    file_edge = detect_file_lineage(
        source_path="packages/react-dom/old-client.js",
        target_path="packages/react-dom/client.js",
        source_content="function createRoot() { return supportsFallback && hasContainer; }",
        target_content="function createRoot() { return supportsFallback && hasContainer; }",
    )
    symbol_edge = detect_symbol_lineage(
        source_symbol="legacyCreateRoot",
        target_symbol="ReactDOM.createRoot",
        source_body="return supportsFallback && hasContainer",
        target_body="return supportsFallback && hasContainer",
    )
    condition = build_condition_history_entry(
        commit_sha="abc1234",
        file_path="packages/react-dom/client.js",
        symbol_name="ReactDOM.createRoot",
        before_expression="supportsFallback",
        after_expression="supportsFallback && hasContainer",
        branch_body_excerpt="preserve fallback path",
        related_tests=("ReactDOM.createRoot.test",),
    )
    rationale = separate_rationale(
        introduction_evidence="Review required the fallback guard.",
        maintenance_evidence="A later test keeps the fallback path covered.",
        current_state="maintained",
    )
    answer = build_lineage_answer(
        origin_candidates=candidates,
        rationale=rationale,
        condition_history=(condition,),
    )
    passed = (
        len(candidates) == 1
        and file_edge.relation_kind is LineageRelationKind.MOVED
        and symbol_edge.relation_kind is LineageRelationKind.RENAMED
        and condition.related_tests == ("ReactDOM.createRoot.test",)
        and answer.status.value == "answered"
    )
    return {
        "status": "lineage_smoke_passed" if passed else "lineage_smoke_failed",
        "origin_candidates": [candidate.to_dict() for candidate in candidates],
        "file_lineage": file_edge.to_dict(),
        "symbol_lineage": symbol_edge.to_dict(),
        "condition_history": condition.to_dict(),
        "rationale": rationale.to_dict(),
        "answer": answer.to_dict(),
    }


def run_local_smoke() -> dict[str, object]:
    """Run all deterministic local smoke checks."""

    stability = run_stability_smoke()
    incident = run_incident_smoke()
    lineage = run_lineage_smoke()
    passed = (
        stability["status"] == "stability_smoke_passed"
        and incident["status"] == "incident_smoke_passed"
        and lineage["status"] == "lineage_smoke_passed"
    )
    return {
        "status": "local_smoke_passed" if passed else "local_smoke_failed",
        "stability": stability,
        "incident": incident,
        "lineage": lineage,
    }


def main() -> None:
    print(json.dumps(run_local_smoke(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
