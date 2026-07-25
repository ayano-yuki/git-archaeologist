from __future__ import annotations

from pathlib import Path
import unittest

from git_archaeologist.evaluation_dataset import (
    EVALUATION_DATASET_SCHEMA_VERSION,
    EvaluationDatasetViolation,
    EvaluationRecord,
    EvaluationScenario,
    ExpectedTarget,
    RiskLabel,
    load_evaluation_jsonl,
    validate_dataset_coverage,
)


DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "baseline-rag"
    / "eval"
    / "repository-specific"
    / "mvp-evaluation.jsonl"
)


class EvaluationDatasetTests(unittest.TestCase):
    def test_validates_repository_specific_record(self) -> None:
        record = EvaluationRecord(
            schema_version=EVALUATION_DATASET_SCHEMA_VERSION,
            record_id="eval-react-react-0001",
            source_repository="react/react",
            scenario=EvaluationScenario.IMPLEMENTATION_RATIONALE,
            question="Why was this guard added?",
            expected_target=ExpectedTarget(
                repository_id="react/react",
                target_type="pull_request",
                artifact_ids=("pr-reviewed-guard",),
                file_path="packages/react-dom/client.js",
            ),
            required_evidence_ids=("review-guard",),
            allowed_inferences=("The guard was related to compatibility.",),
            risk_label=RiskLabel.UNKNOWN,
            split="test",
        )

        self.assertEqual("eval-react-react-0001", record.to_dict()["record_id"])

    def test_rejects_answerable_case_without_required_evidence(self) -> None:
        with self.assertRaises(EvaluationDatasetViolation):
            EvaluationRecord(
                schema_version=EVALUATION_DATASET_SCHEMA_VERSION,
                record_id="bad",
                source_repository="react/react",
                scenario=EvaluationScenario.CHANGE_RISK,
                question="Is this risky?",
                expected_target=ExpectedTarget("react/react", "pull_request", ("pr-risk",)),
                required_evidence_ids=(),
                allowed_inferences=(),
                risk_label=RiskLabel.RISK_FOUND,
                split="test",
            )

    def test_seed_dataset_is_git_managed_shape_and_covers_mvp_edge_cases(self) -> None:
        records = load_evaluation_jsonl(DATASET_PATH)

        validate_dataset_coverage(records)
        self.assertEqual(5, len(records))
        self.assertTrue(all(record.source_repository == "react/react" for record in records))
        self.assertIn(EvaluationScenario.MULTIPLE_CANDIDATES, {record.scenario for record in records})
        self.assertIn(EvaluationScenario.INSUFFICIENT_EVIDENCE, {record.scenario for record in records})
        self.assertIn(EvaluationScenario.FALSE_WARNING, {record.scenario for record in records})

    def test_insufficient_evidence_cases_use_unknown_risk_label(self) -> None:
        with self.assertRaises(EvaluationDatasetViolation):
            EvaluationRecord(
                schema_version=EVALUATION_DATASET_SCHEMA_VERSION,
                record_id="bad-insufficient",
                source_repository="react/react",
                scenario=EvaluationScenario.INSUFFICIENT_EVIDENCE,
                question="Why?",
                expected_target=ExpectedTarget("react/react", "symbol", ("symbol-missing",)),
                required_evidence_ids=(),
                allowed_inferences=(),
                risk_label=RiskLabel.NO_RISK_FOUND,
                split="test",
            )


if __name__ == "__main__":
    unittest.main()
