from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from git_archaeologist.chat.chat_flow import (
    ChatEvidenceItem,
    ChatEvidencePack,
    ChatTarget,
)
from git_archaeologist.chat.routing import (
    ChatSessionState,
    ChatRoute,
    build_unified_citations,
    check_session_freshness,
    route_chat_query,
)
from git_archaeologist.evaluation.production_training import (
    build_production_training_readiness,
    discover_production_collection_summaries,
)
from git_archaeologist.ops.operations import (
    OperationStatus,
    build_local_operations_plan,
    build_protected_data_inventory,
    build_regression_suite_plan,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/baseline-rag/sft/answer-discipline/lora-training-plan.json"


class ChatRoutingTests(unittest.TestCase):
    def test_integrated_routing_combines_lineage_incident_and_risk(self) -> None:
        result = route_chat_query(
            "\n".join(
                (
                    "https://github.com/facebook/react/pull/12345",
                    "file: packages/react-dom/src/client/ReactDOMRoot.js",
                    "Question: does changing this condition risk a CI failure or revert?",
                )
            )
        )

        self.assertEqual(ChatRoute.COMBINED, result.route)
        self.assertIn("lineage-origin-maintenance", result.query_plan_ids)
        self.assertIn("incident-causal-history", result.query_plan_ids)
        self.assertIn("historical-change-risk", result.query_plan_ids)
        self.assertTrue(result.requires_current_change)

    def test_unified_citations_are_stable_across_artifact_kinds(self) -> None:
        pack = ChatEvidencePack(
            pack_id="pack-1",
            index_version="index-v2",
            items=(
                ChatEvidenceItem(
                    source_id="pr-123",
                    source_url="https://github.com/facebook/react/pull/123",
                    text="Pull request rationale.",
                    parent_event_id="event-pr-123",
                ),
                ChatEvidenceItem(
                    source_id="ci-456",
                    source_url="https://github.com/facebook/react/actions/runs/456",
                    text="CI failure details.",
                    parent_event_id="event-ci-456",
                ),
            ),
        )

        citations = build_unified_citations(pack)

        self.assertEqual(("C1", "C2"), tuple(citation.citation_id for citation in citations))
        self.assertEqual("pull_request", citations[0].artifact_kind)
        self.assertEqual("ci", citations[1].artifact_kind)

    def test_session_freshness_rejects_old_index_or_head(self) -> None:
        session = ChatSessionState(
            session_id="session-1",
            repository="facebook/react",
            target=ChatTarget(target_id="target-1", target_type="file"),
            head_sha="old-head",
            evidence_pack_id="pack-1",
            index_version="index-v1",
            updated_at="2026-07-26T00:00:00+00:00",
        )

        freshness = check_session_freshness(
            session,
            current_index_version="index-v2",
            current_head_sha="new-head",
        )

        self.assertFalse(freshness.can_reuse)
        self.assertEqual(("index_version", "head_sha"), freshness.stale_fields)

    def test_production_collection_summaries_are_discovered(self) -> None:
        summaries = discover_production_collection_summaries(ROOT / "data/local-runtime/runs")

        self.assertGreaterEqual(len(summaries), 3)
        self.assertTrue(all(summary.passed for summary in summaries))
        self.assertIn("react/react", {summary.repository_id for summary in summaries})

    def test_production_training_readiness_passes_with_recorded_runs(self) -> None:
        readiness = build_production_training_readiness(
            runs_root=ROOT / "data/local-runtime/runs",
            plan_path=PLAN_PATH,
            dependency_names=(),
        )

        self.assertTrue(readiness.ready)
        self.assertEqual("react/react", readiness.repository_id)
        self.assertEqual((), readiness.missing_artifact_kinds)
        self.assertGreater(readiness.collected_artifact_count, 0)
        self.assertIn("--execute", readiness.execute_command)

    def test_production_training_readiness_blocks_when_artifacts_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runs_root = Path(temp_dir) / "runs"
            run_dir = runs_root / "react-react-production-small"
            run_dir.mkdir(parents=True)
            (run_dir / "collection-summary.json").write_text(
                """{
                  "run_id": "react-react-production-small",
                  "repository_id": "react/react",
                  "passed": true,
                  "collected_artifact_count": 1,
                  "artifact_counts": {"commit": 1},
                  "manifest_path": "manifest.jsonl"
                }""",
                encoding="utf-8",
            )

            readiness = build_production_training_readiness(
                runs_root=runs_root,
                plan_path=PLAN_PATH,
                dependency_names=(),
            )

        self.assertFalse(readiness.ready)
        self.assertIn("pull_request", readiness.missing_artifact_kinds)

    def test_local_operations_plan_covers_setup_sync_training_and_qa(self) -> None:
        plan = build_local_operations_plan()

        self.assertEqual(OperationStatus.PENDING, plan.status)
        self.assertTrue(plan.setup_steps)
        self.assertTrue(plan.sync_steps)
        self.assertTrue(plan.training_steps)
        self.assertTrue(plan.qa_steps)
        self.assertIn("production-training-execute", {step.step_id for step in plan.training_steps})

    def test_data_inventory_and_regression_suite_are_explicit(self) -> None:
        inventory = build_protected_data_inventory(data_root=ROOT / "data")
        suite = build_regression_suite_plan()

        self.assertTrue(inventory.redaction_required)
        self.assertTrue(any("local-runtime" in root for root in inventory.data_roots))
        self.assertIn("authorization_header", inventory.protected_patterns)
        self.assertIn("unittest discover tests", suite.commands[0])
        self.assertTrue(suite.required_reports)


if __name__ == "__main__":
    unittest.main()
