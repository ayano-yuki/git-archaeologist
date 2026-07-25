"""Deterministic Phase3 smoke check for incident and Revert analysis."""

from __future__ import annotations

import json

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
from git_archaeologist.rag.incident_answering import (
    build_incident_answer,
    evaluate_historical_risk,
)


def run_phase3_smoke() -> dict[str, object]:
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
        introducing_change=IncidentNode("commit-abc1234", "change", "2026-01-01T00:00:00Z", "Add createRoot guard", "packages/react-dom/client.js", "ReactDOM.createRoot", "https://github.com/react/react/commit/abc1234"),
        failure=IncidentNode(signature.signature_id, "ci_failure", failure.occurred_at, failure.message, "packages/react-dom/client.js", "ReactDOM.createRoot", failure.source_url),
        fix=IncidentNode("commit-fix", "fix", "2026-01-03T00:00:00Z", "Preserve fallback path", "packages/react-dom/client.js", "ReactDOM.createRoot", "https://github.com/react/react/commit/fix"),
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
        "status": "phase3_smoke_passed" if passed else "phase3_smoke_failed",
        "ci_failure": failure.to_dict(),
        "signature": signature.to_dict(),
        "revert": revert.to_dict(),
        "incident_graph": graph.to_dict(),
        "answer": answer.to_dict(),
        "historical_risk": risk.to_dict(),
    }


def main() -> None:
    print(json.dumps(run_phase3_smoke(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
