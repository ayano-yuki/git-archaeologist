from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from git_archaeologist.evaluation.production_sft_dataset import (
    build_production_sft_records,
    write_production_sft_dataset,
)
from git_archaeologist.evaluation.sft_dataset import validate_sft_dataset
from git_archaeologist.evaluation.sft_training_plan import load_sft_training_plan


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DATASET_PATH = (
    ROOT
    / "data/Qwen--Qwen2.5-Coder-7B-Instruct/sft/answer-discipline/production-sft-records.jsonl"
)
PRODUCTION_PLAN_PATH = (
    ROOT
    / "data/Qwen--Qwen2.5-Coder-7B-Instruct/sft/answer-discipline/production-lora-training-plan.json"
)


class ProductionSFTDatasetTests(unittest.TestCase):
    def test_build_groups_related_artifacts_into_one_split(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_root = Path(temp_dir) / "raw"
            _write_artifact(
                raw_root,
                "pull_request",
                "pull_request-1",
                {
                    "number": 1,
                    "title": "Keep member updates stable",
                    "state": "OPEN",
                    "baseRefName": "main",
                    "headRefName": "member-updates",
                    "body": "The change preserves update semantics.",
                    "url": "https://github.com/react/react/pull/1",
                },
            )
            _write_artifact(
                raw_root,
                "review_comment",
                "review_comment-10",
                {
                    "body": "Avoid widening the risk claim beyond this line.",
                    "html_url": "https://github.com/react/react/pull/1#discussion_r10",
                    "pull_request_url": "https://api.github.com/repos/react/react/pulls/1",
                    "path": "packages/example.js",
                },
            )

            records = build_production_sft_records(raw_root)

        self.assertEqual(2, len(records))
        self.assertEqual({record["split"] for record in records}, {records[0]["split"]})
        self.assertEqual(
            {"pr:1"},
            {record["target"]["decision_id"] for record in records},  # type: ignore[index]
        )
        self.assertIn("Evidence Pack", records[0]["question"])

    def test_write_outputs_dataset_plan_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            raw_root = temp_root / "raw"
            _write_artifact(
                raw_root,
                "ci_run",
                "ci_run-100",
                {
                    "databaseId": 100,
                    "workflowName": "Tests",
                    "displayTitle": "Unit tests",
                    "event": "pull_request",
                    "status": "completed",
                    "conclusion": "success",
                    "headSha": "abc123",
                    "url": "https://github.com/react/react/actions/runs/100",
                },
            )

            dataset_path = temp_root / "records.jsonl"
            plan_path = temp_root / "plan.json"
            summary_path = temp_root / "summary.json"
            summary = write_production_sft_dataset(
                raw_root=raw_root,
                dataset_path=dataset_path,
                plan_path=plan_path,
                summary_path=summary_path,
                output_dir=temp_root / "model",
            )

            self.assertEqual("production_sft_dataset_ready", summary.status)
            self.assertEqual(1, validate_sft_dataset(dataset_path).record_count)
            self.assertEqual(dataset_path.as_posix(), load_sft_training_plan(plan_path).dataset_path)
            self.assertTrue(summary_path.exists())

    def test_checked_in_production_dataset_and_plan_validate(self) -> None:
        if not PRODUCTION_DATASET_PATH.exists() or not PRODUCTION_PLAN_PATH.exists():
            self.skipTest("production SFT dataset has not been generated")

        report = validate_sft_dataset(PRODUCTION_DATASET_PATH)
        plan = load_sft_training_plan(PRODUCTION_PLAN_PATH)

        self.assertGreater(report.record_count, 2)
        self.assertEqual(PRODUCTION_DATASET_PATH.relative_to(ROOT).as_posix(), plan.dataset_path)
        self.assertEqual("Qwen/Qwen2.5-Coder-7B-Instruct", plan.base_model)


def _write_artifact(
    raw_root: Path,
    kind: str,
    external_id: str,
    raw: dict[str, object],
) -> None:
    artifact_dir = raw_root / kind
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{external_id}.json"
    payload = {
        "schema_version": 1,
        "repository_id": "react/react",
        "artifact_kind": kind,
        "external_id": external_id,
        "source_url": raw.get("html_url") or raw.get("url") or f"https://github.com/react/react/{external_id}",
        "raw": raw,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
