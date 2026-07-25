from __future__ import annotations

import unittest

from git_archaeologist.normalization.ci_failures import (
    CIRetentionPolicy,
    generate_failure_signature,
    parse_ci_failure_event,
    redact_ci_log,
)
from git_archaeologist.normalization.incident_graph import (
    ConstraintState,
    IncidentNode,
    RevertState,
    build_incident_graph,
    detect_revert_state,
)
from git_archaeologist.phase3_smoke import run_phase3_smoke
from git_archaeologist.rag.incident_answering import (
    build_incident_answer,
    evaluate_historical_risk,
)


class Phase3IncidentTests(unittest.TestCase):
    def test_ci_log_policy_redacts_and_truncates(self) -> None:
        redacted = redact_ci_log("token=secret-value\nAssertionError: boom", CIRetentionPolicy(max_excerpt_bytes=30))

        self.assertIn("<redacted>", redacted)
        self.assertNotIn("secret-value", redacted)
        self.assertLessEqual(len(redacted.encode("utf-8")), 30)

    def test_ci_failure_event_and_signature_are_stable(self) -> None:
        event = parse_ci_failure_event(
            repository_id="react/react",
            workflow_name="CI",
            job_name="unit",
            step_name="test",
            head_sha="abc1234",
            occurred_at="2026-01-02T00:00:00Z",
            source_url="https://github.com/react/react/actions/runs/1",
            log_text="FAIL ReactDOM.test\nAssertionError: expected 42 at abc1234\npackages/react-dom/client.js:120",
        )
        same_event = parse_ci_failure_event(
            repository_id="react/react",
            workflow_name="CI",
            job_name="unit",
            step_name="test",
            head_sha="abc1234",
            occurred_at="2026-01-02T00:00:00Z",
            source_url="https://github.com/react/react/actions/runs/1",
            log_text="FAIL ReactDOM.test\nAssertionError: expected 43 at deadbee\npackages/react-dom/client.js:999",
        )

        self.assertEqual("ReactDOM.test", event.test_name)
        self.assertEqual("AssertionError", event.error_class)
        self.assertEqual(
            generate_failure_signature(event).signature_id,
            generate_failure_signature(same_event).signature_id,
        )

    def test_revert_detection_distinguishes_partial_and_reapply(self) -> None:
        partial = detect_revert_state("Revert change\n\nThis reverts commit abc1234", patch_reverse_similarity=0.4)
        reapply = detect_revert_state("Reland createRoot guard", reapplied_later=True)

        self.assertEqual(RevertState.PARTIALLY_REVERTED, partial.state)
        self.assertEqual(RevertState.REAPPLIED, reapply.state)

    def test_incident_graph_tracks_constraint_and_answer(self) -> None:
        graph = build_incident_graph(
            incident_id="incident-1",
            introducing_change=IncidentNode("commit-1", "change", "2026-01-01T00:00:00Z", "Add guard", "a.js", "guard", "https://example.test/commit-1"),
            failure=IncidentNode("failure-1", "ci_failure", "2026-01-02T00:00:00Z", "AssertionError", "a.js", "guard", "https://example.test/failure"),
            fix=IncidentNode("fix-1", "fix", "2026-01-03T00:00:00Z", "Fix guard", "a.js", "guard", "https://example.test/fix"),
        )
        answer = build_incident_answer(graph)

        self.assertEqual(ConstraintState.MAINTAINED, graph.constraint_state)
        self.assertIsNotNone(answer.observed_cause)
        self.assertIn("failure-1", answer.related_failures)

    def test_historical_risk_suppresses_same_file_only(self) -> None:
        graph = build_incident_graph(
            incident_id="incident-1",
            introducing_change=IncidentNode("commit-1", "change", "2026-01-01T00:00:00Z", "Add guard", "a.js", "guard"),
            failure=IncidentNode("failure-1", "ci_failure", "2026-01-02T00:00:00Z", "AssertionError", "a.js", "guard"),
        )

        finding = evaluate_historical_risk(
            changed_files=("a.js",),
            changed_symbols=("other",),
            failure_signature_ids=(),
            incident_graphs=(graph,),
        )

        self.assertFalse(finding.risk_found)
        self.assertEqual("same_file_only", finding.suppressed_reason)

    def test_phase3_smoke_passes(self) -> None:
        self.assertEqual("phase3_smoke_passed", run_phase3_smoke()["status"])


if __name__ == "__main__":
    unittest.main()
