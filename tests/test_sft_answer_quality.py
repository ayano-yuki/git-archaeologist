from __future__ import annotations

import unittest
from pathlib import Path

from git_archaeologist.evaluation.sft_answer_quality import (
    AnswerQualityThresholds,
    build_answer_quality_report,
    build_sft_inference_prompt,
    evaluate_generated_answer,
    parse_generated_answer,
)
from git_archaeologist.evaluation.sft_dataset import load_sft_jsonl


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data/baseline-rag/sft/answer-discipline/sft-records.jsonl"


class SFTAnswerQualityTests(unittest.TestCase):
    def test_inference_prompt_matches_training_prefix_without_answer(self) -> None:
        record = load_sft_jsonl(DATASET_PATH)[0]

        prompt = build_sft_inference_prompt(record)

        self.assertIn("Answer only from the Evidence Pack", prompt)
        self.assertIn("### Evidence Pack", prompt)
        self.assertTrue(prompt.endswith("### Ideal Answer\n"))
        self.assertNotIn("The evidence supports saying", prompt)

    def test_parse_generated_answer_extracts_json_from_text(self) -> None:
        parsed = parse_generated_answer(
            'Here is the answer:\n{"answer":"Supported only.","citations":["review-demo-1"],"unsupported_claims":[],"confidence":"medium"}'
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(["review-demo-1"], parsed["citations"])  # type: ignore[index]

    def test_evaluate_generated_answer_passes_schema_and_citations(self) -> None:
        record = load_sft_jsonl(DATASET_PATH)[0]
        generation = (
            '{"answer":"The review requested a guard; the root cause is unknown.",'
            '"citations":["review-demo-1"],"unsupported_claims":[],"confidence":"medium"}'
        )

        result = evaluate_generated_answer(record, generation)

        self.assertTrue(result.passed)
        self.assertTrue(result.expected_citation_recall_passed)
        self.assertEqual((), result.failure_reasons)

    def test_evaluate_generated_answer_flags_unknown_citation(self) -> None:
        record = load_sft_jsonl(DATASET_PATH)[0]
        generation = (
            '{"answer":"Unsupported.",'
            '"citations":["missing-source"],"unsupported_claims":["root cause"],"confidence":"certain"}'
        )

        result = evaluate_generated_answer(record, generation)

        self.assertFalse(result.passed)
        self.assertIn("citations were empty or referenced unknown source IDs", result.failure_reasons)
        self.assertIn("confidence was missing or invalid", result.failure_reasons)

    def test_report_aggregates_thresholds(self) -> None:
        record = load_sft_jsonl(DATASET_PATH)[0]
        result = evaluate_generated_answer(
            record,
            '{"answer":"Supported.","citations":["review-demo-1"],"unsupported_claims":[],"confidence":"medium"}',
        )

        report = build_answer_quality_report(
            plan_path=ROOT / "plan.json",
            adapter_dir=ROOT / "adapter",
            dataset_path=DATASET_PATH,
            split="validation",
            results=(result,),
            thresholds=AnswerQualityThresholds(),
        )

        self.assertEqual("answer_quality_passed", report.status)
        self.assertEqual(1.0, report.metrics["parse_success_rate"])
        self.assertEqual(1.0, report.metrics["pass_rate"])


if __name__ == "__main__":
    unittest.main()
