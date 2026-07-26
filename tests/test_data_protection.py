from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from git_archaeologist.ops.data_protection import (
    DataProtectionStatus,
    build_backup_plan,
    build_data_protection_inventory,
    build_delete_plan,
    report_to_json,
)
from git_archaeologist.ops.operations import build_local_operations_plan
from git_archaeologist.ops.phase5_operations import build_phase5_operations_report


class DataProtectionTests(unittest.TestCase):
    def test_inventory_lists_raw_runs_models_and_eval_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            _write_json(data_root / "local-runtime/raw/react/react/pull_request/pr-1.json", {"id": 1})
            _write_json(data_root / "local-runtime/runs/react-react-production-1/collection-summary.json", {"passed": True})
            _write_json(data_root / "Qwen--Qwen2.5-Coder-7B-Instruct/models/adapter/adapter_config.json", {"r": 16})
            _write_json(data_root / "Qwen--Qwen2.5-Coder-7B-Instruct/eval/post-sft/report.json", {"passed": True})

            report = build_data_protection_inventory(repository_id="react/react", data_root=data_root)

        self.assertEqual(DataProtectionStatus.READY, report.status)
        categories = {path.category.value for path in report.paths}
        self.assertLessEqual({"raw", "runs", "models", "eval"}, categories)
        existing = {Path(path.path).name for path in report.paths if path.exists}
        self.assertIn("react", existing)
        self.assertFalse(report.redaction_blocked)

    def test_delete_plan_is_dry_run_and_stays_inside_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            target = data_root / "local-runtime/raw/react/react/pull_request/pr-1.json"
            _write_json(target, {"id": 1})

            report = build_delete_plan(repository_id="react/react", data_root=data_root)

            self.assertTrue(target.exists())

        self.assertEqual(DataProtectionStatus.READY, report.status)
        self.assertTrue(report.dry_run)
        self.assertEqual((), report.blocked_paths)
        self.assertTrue(report.target_paths)
        self.assertEqual((), report.executed_paths)

    def test_secret_like_field_blocks_without_exposing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            _write_json(
                data_root / "local-runtime/raw/react/react/issue/issue-1.json",
                {"authorization_header": "Bearer should-not-leak"},
            )

            report = build_delete_plan(repository_id="react/react", data_root=data_root)
            payload = report_to_json(report)

        self.assertEqual(DataProtectionStatus.BLOCKED, report.status)
        self.assertIn("authorization_header", payload)
        self.assertNotIn("should-not-leak", payload)

    def test_tokenizer_vocab_words_are_not_treated_as_secret_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            _write_json(
                data_root / "Qwen--Qwen2.5-Coder-7B-Instruct/models/adapter/vocab.json",
                {"password": 1, "AccessToken": 2},
            )

            report = build_data_protection_inventory(repository_id="react/react", data_root=data_root)

        self.assertEqual(DataProtectionStatus.READY, report.status)
        self.assertEqual((), report.secret_like_findings)

    def test_delete_execute_requires_matching_repository_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            target = data_root / "local-runtime/raw/react/react/issue/issue-1.json"
            _write_json(target, {"id": 1})

            report = build_delete_plan(
                repository_id="react/react",
                data_root=data_root,
                execute=True,
                confirm_repository_id=None,
            )

            self.assertTrue(target.exists())

        self.assertEqual(DataProtectionStatus.BLOCKED, report.status)
        self.assertIn("confirm", report.reason)

    def test_backup_plan_is_descriptive_and_does_not_copy_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            _write_json(data_root / "local-runtime/raw/react/react/issue/issue-1.json", {"id": 1})

            report = build_backup_plan(repository_id="react/react", data_root=data_root)

        self.assertEqual(DataProtectionStatus.READY, report.status)
        self.assertTrue(report.dry_run)
        self.assertTrue(report.source_paths)
        self.assertIn("backup-manifest.json", report.manifest_path)

    def test_operations_plan_exposes_data_protection_command(self) -> None:
        plan = build_local_operations_plan()
        commands = [step.command for step in plan.setup_steps]

        self.assertIn(
            "uv --system-certs run python -m git_archaeologist.ops.data_protection --inventory",
            commands,
        )

    def test_phase5_operations_report_includes_data_protection_commands(self) -> None:
        report = build_phase5_operations_report()

        self.assertIn("data_protection --delete-plan", " ".join(report.data_protection_commands))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
