from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from git_archaeologist.ops.incremental_sync import (
    ArtifactSyncKind,
    ArtifactUpdate,
    SyncState,
    SyncWatermark,
)
from git_archaeologist.ops.phase5_sync import (
    build_default_sync_state,
    build_phase5_manual_sync_plan_report,
    build_phase5_sync_status_report,
    build_scheduler_config,
    load_observed_updates,
    load_sync_state,
    report_to_json,
)


class Phase5SyncTests(unittest.TestCase):
    def test_status_report_exposes_repository_index_and_watermarks(self) -> None:
        state = build_default_sync_state(
            repository_id="react/react",
            index_version="index-v7",
            synced_at="2026-07-26T00:00:00+00:00",
        )

        report = build_phase5_sync_status_report(state)
        payload = report.to_dict()

        self.assertEqual("phase5_sync_status_ready", report.status)
        self.assertEqual("react/react", payload["repository_id"])
        self.assertEqual("index-v7", payload["index_version"])
        self.assertTrue(payload["watermarks"])
        self.assertIn("manual_sync_command", payload)

    def test_manual_plan_selects_changed_and_skips_unchanged_updates(self) -> None:
        state = SyncState(
            repository_id="react/react",
            index_version="index-v1",
            synced_at="2026-07-26T00:00:00+00:00",
            watermarks=(
                SyncWatermark(
                    artifact_kind=ArtifactSyncKind.PULL_REQUEST,
                    updated_at="2026-07-26T00:00:00+00:00",
                    head_sha="old",
                ),
            ),
        )
        updates = (
            ArtifactUpdate(
                artifact_kind=ArtifactSyncKind.PULL_REQUEST,
                artifact_id="pr-1",
                updated_at="2026-07-26T00:00:00+00:00",
                head_sha="old",
            ),
            ArtifactUpdate(
                artifact_kind=ArtifactSyncKind.PULL_REQUEST,
                artifact_id="pr-2",
                updated_at="2026-07-26T00:01:00+00:00",
                head_sha="new",
            ),
        )

        report = build_phase5_manual_sync_plan_report(state, updates)
        payload = report.to_dict()

        self.assertEqual("phase5_manual_sync_plan_ready", report.status)
        self.assertEqual(2, payload["observed_update_count"])
        self.assertEqual(("pr-1",), report.skipped_artifact_ids)
        self.assertEqual("pr-2", report.selected_updates[0]["artifact_id"])
        self.assertFalse(report.external_collection_executed)

    def test_scheduler_config_is_descriptive_and_does_not_mutate_external_scheduler(self) -> None:
        scheduler = build_scheduler_config(enabled=True, interval_minutes=30)

        self.assertTrue(scheduler.enabled)
        self.assertEqual(30, scheduler.interval_minutes)
        self.assertFalse(scheduler.mutates_external_scheduler)
        self.assertIn("phase5_sync --plan", scheduler.command)

    def test_state_and_observed_updates_can_be_loaded_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            updates_path = Path(temp_dir) / "updates.json"
            state_path.write_text(
                json.dumps(
                    {
                        "repository_id": "react/react",
                        "index_version": "index-v2",
                        "synced_at": "2026-07-26T00:00:00+00:00",
                        "watermarks": [
                            {
                                "artifact_kind": "issue",
                                "updated_at": "2026-07-26T00:00:00+00:00",
                                "cursor": "cursor-1",
                                "head_sha": None,
                            }
                        ],
                        "tombstones": ["issue-closed"],
                    }
                ),
                encoding="utf-8",
            )
            updates_path.write_text(
                json.dumps(
                    [
                        {
                            "artifact_kind": "issue",
                            "artifact_id": "issue-1",
                            "updated_at": "2026-07-26T00:02:00+00:00",
                            "cursor": "cursor-2",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            state = load_sync_state(state_path)
            updates = load_observed_updates(updates_path)

        self.assertEqual("index-v2", state.index_version)
        self.assertEqual(("issue-closed",), state.tombstones)
        self.assertEqual("issue-1", updates[0].artifact_id)

    def test_reports_are_json_serializable(self) -> None:
        state = build_default_sync_state()
        text = report_to_json(build_phase5_sync_status_report(state))

        payload = json.loads(text)
        self.assertEqual("phase5_sync_status_ready", payload["status"])


if __name__ == "__main__":
    unittest.main()
