from __future__ import annotations

import json
import unittest
from pathlib import Path

from git_archaeologist.evaluation.leakage_evaluation import (
    ClosedBookPrediction,
    evaluate_closed_book_leakage,
)
from git_archaeologist.evaluation.reranker_training import (
    EvidenceCandidate,
    RankingTrainingExample,
    evaluate_keyword_reranker,
    train_keyword_reranker_profile,
)
from git_archaeologist.evaluation.sft_data_policy import ExpectedVerdict, validate_evaluation_case
from git_archaeologist.evaluation.sft_dataset import validate_sft_dataset
from git_archaeologist.evaluation.sft_training_plan import (
    SFTTrainingStatus,
    build_sft_training_plan,
    load_sft_training_plan,
)


ROOT = Path(__file__).resolve().parents[1]


class PhaseOptionalsTests(unittest.TestCase):
    def test_reviewed_sft_dataset_validates(self) -> None:
        report = validate_sft_dataset(ROOT / "data/baseline-rag/sft/answer-discipline/sft-records.jsonl")

        self.assertEqual(2, report.record_count)
        self.assertEqual(1, report.split_counts["train"])
        self.assertEqual(1, report.split_counts["validation"])
        self.assertEqual(
            ("sft-answer-discipline-0001", "sft-answer-discipline-0002"),
            report.record_ids,
        )

    def test_closed_book_leakage_cases_require_unknown(self) -> None:
        cases = tuple(
            validate_evaluation_case(raw_case)
            for raw_case in _load_jsonl(ROOT / "data/baseline-rag/eval/closed-book/closed-book-cases.jsonl")
        )
        predictions = tuple(
            ClosedBookPrediction(
                case_id=case.case_id,
                verdict=ExpectedVerdict.UNKNOWN.value,
                answer="Evidence Pack is empty, so the repository fact is unknown.",
            )
            for case in cases
        )

        report = evaluate_closed_book_leakage(cases, predictions)

        self.assertTrue(report.passed)
        self.assertEqual(2, report.evaluated_case_count)

    def test_closed_book_leakage_detects_forbidden_claims(self) -> None:
        case = validate_evaluation_case(_load_jsonl(ROOT / "data/baseline-rag/eval/closed-book/closed-book-cases.jsonl")[0])

        report = evaluate_closed_book_leakage(
            (case,),
            (
                ClosedBookPrediction(
                    case_id=case.case_id,
                    verdict="answerable",
                    answer="A production incident caused the guard.",
                    cited_source_ids=("missing-source",),
                ),
            ),
        )

        self.assertFalse(report.passed)
        self.assertEqual(3, report.finding_count)

    def test_reranker_training_promotes_positive_evidence(self) -> None:
        examples = tuple(
            _ranking_example(raw_example)
            for raw_example in _load_jsonl(ROOT / "data/baseline-rag/eval/reranker-training/ranking-examples.jsonl")
        )

        profile = train_keyword_reranker_profile(examples)
        report = evaluate_keyword_reranker(profile, examples)

        self.assertTrue(report.passed)
        self.assertEqual(1.0, report.mean_reciprocal_rank)
        self.assertEqual(2, report.positive_first_count)

    def test_sft_training_plan_defers_when_phase2_decision_defers(self) -> None:
        decision_record = json.loads(
            (ROOT / "data/baseline-rag/eval/phase2/stabilization-decision.json").read_text(encoding="utf-8")
        )["sft_decision"]

        plan = build_sft_training_plan(
            decision_record,
            dataset_path=ROOT / "data/baseline-rag/sft/answer-discipline/sft-records.jsonl",
            output_dir=ROOT / "data/baseline-rag/models/answer-discipline-qlora",
            base_model="local-7b-to-14b-instruct",
        )

        self.assertEqual(SFTTrainingStatus.DEFERRED, plan.status)
        self.assertFalse(plan.should_train)
        self.assertIn("defer_sft", plan.reason)

        recorded_plan = load_sft_training_plan(
            ROOT / "data/baseline-rag/sft/answer-discipline/lora-training-plan.json"
        )
        self.assertEqual(SFTTrainingStatus.READY, recorded_plan.status)
        self.assertEqual("Qwen/Qwen2.5-Coder-7B-Instruct", recorded_plan.base_model)
        self.assertEqual(str(ROOT / "data/baseline-rag/sft/answer-discipline/sft-records.jsonl"), plan.dataset_path)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ranking_example(raw_example: dict[str, object]) -> RankingTrainingExample:
    positive = raw_example["positive"]
    hard_negatives = raw_example["hard_negatives"]
    if not isinstance(positive, dict):
        raise TypeError("positive must be an object")
    if not isinstance(hard_negatives, list):
        raise TypeError("hard_negatives must be a list")
    return RankingTrainingExample(
        query=str(raw_example["query"]),
        positive=EvidenceCandidate(str(positive["evidence_id"]), str(positive["text"])),
        hard_negatives=tuple(
            EvidenceCandidate(str(negative["evidence_id"]), str(negative["text"]))
            for negative in hard_negatives
            if isinstance(negative, dict)
        ),
    )


if __name__ == "__main__":
    unittest.main()
