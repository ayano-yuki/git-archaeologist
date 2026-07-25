from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from git_archaeologist.evaluation.post_sft_evaluation import (
    build_post_sft_evaluation_report,
    post_sft_evaluation_report_to_dict,
    validate_adapter_artifacts,
    write_post_sft_evaluation_report,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/baseline-rag/sft/answer-discipline/lora-training-plan.json"
ADAPTER_DIR = ROOT / "data/Qwen--Qwen2.5-Coder-7B-Instruct/models/answer-discipline-qlora"
CLOSED_BOOK_CASES = ROOT / "data/baseline-rag/eval/closed-book/closed-book-cases.jsonl"
PHASE2_DECISION = ROOT / "data/baseline-rag/eval/phase2/stabilization-decision.json"


class PostSFTEvaluationTests(unittest.TestCase):
    def test_adapter_artifact_validation_passes_for_checked_in_outputs(self) -> None:
        report = validate_adapter_artifacts(ADAPTER_DIR)

        self.assertTrue(report.passed)
        self.assertEqual((), report.missing_files)
        self.assertEqual("sft_training_completed", report.training_status)
        self.assertEqual("Qwen/Qwen2.5-Coder-7B-Instruct", report.base_model)
        self.assertEqual(1, report.record_count)
        self.assertIsNotNone(report.train_loss)

    def test_adapter_artifact_validation_detects_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter_dir = Path(temp_dir)
            (adapter_dir / "training-run-summary.json").write_text(
                json.dumps({"status": "sft_training_completed"}),
                encoding="utf-8",
            )

            report = validate_adapter_artifacts(adapter_dir)

        self.assertFalse(report.passed)
        self.assertIn("adapter_config.json", report.missing_files)
        self.assertIn("adapter_model.safetensors", report.missing_files)

    def test_post_sft_report_passes_and_compares_same_metrics(self) -> None:
        report = build_post_sft_evaluation_report(
            plan_path=PLAN_PATH,
            adapter_dir=ADAPTER_DIR,
            closed_book_cases_path=CLOSED_BOOK_CASES,
            phase2_decision_path=PHASE2_DECISION,
        )
        payload = post_sft_evaluation_report_to_dict(report)

        self.assertEqual("post_sft_evaluation_passed", report.status)
        self.assertTrue(payload["closed_book_leakage"]["passed"])
        self.assertEqual(3, len(payload["comparisons"]))
        sft_row = next(row for row in payload["comparisons"] if row["name"] == "sft-adapter")
        self.assertFalse(sft_row["regression_detected"])
        self.assertEqual(0.0, sft_row["delta_vs_baseline"]["unsupported_claim_rate"])

    def test_post_sft_report_can_be_written(self) -> None:
        report = build_post_sft_evaluation_report(
            plan_path=PLAN_PATH,
            adapter_dir=ADAPTER_DIR,
            closed_book_cases_path=CLOSED_BOOK_CASES,
            phase2_decision_path=PHASE2_DECISION,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = write_post_sft_evaluation_report(report, Path(temp_dir) / "report.json")

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual("post_sft_evaluation_passed", payload["status"])


if __name__ == "__main__":
    unittest.main()
