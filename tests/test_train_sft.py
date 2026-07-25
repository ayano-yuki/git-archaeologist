from __future__ import annotations

import unittest
from pathlib import Path

from git_archaeologist.evaluation.sft_dataset import load_sft_jsonl
from git_archaeologist.evaluation.sft_training_plan import (
    SFTTrainingStatus,
    load_sft_training_plan,
)
from git_archaeologist.evaluation.train_sft import (
    build_dry_run_report,
    build_training_text,
    dry_run_report_to_dict,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/baseline-rag/sft/answer-discipline/lora-training-plan.json"
DATASET_PATH = ROOT / "data/baseline-rag/sft/answer-discipline/sft-records.jsonl"


class TrainSFTTests(unittest.TestCase):
    def test_recorded_plan_is_ready_for_qwen_qlora(self) -> None:
        plan = load_sft_training_plan(PLAN_PATH)

        self.assertEqual(SFTTrainingStatus.READY, plan.status)
        self.assertTrue(plan.should_train)
        self.assertEqual("qlora", plan.method)
        self.assertEqual("Qwen/Qwen2.5-Coder-7B-Instruct", plan.base_model)
        self.assertEqual(4096, plan.training_args["max_seq_length"])

    def test_training_text_preserves_evidence_and_answer_discipline(self) -> None:
        record = load_sft_jsonl(DATASET_PATH)[0]

        text = build_training_text(record)

        self.assertIn("Answer only from the Evidence Pack", text)
        self.assertIn("review-demo-1", text)
        self.assertIn("The evidence supports saying", text)
        self.assertIn("unsupported_claims", text)

    def test_dry_run_report_does_not_require_training_dependencies(self) -> None:
        report = build_dry_run_report(PLAN_PATH, dependency_names=())
        payload = dry_run_report_to_dict(report)

        self.assertEqual("sft_dry_run_passed", report.status)
        self.assertTrue(report.should_train)
        self.assertEqual(2, report.record_count)
        self.assertIn(report.runtime_answer_judge_status, {"ready", "cpu_or_low_vram"})
        self.assertEqual([], payload["missing_optional_dependencies"])


if __name__ == "__main__":
    unittest.main()
