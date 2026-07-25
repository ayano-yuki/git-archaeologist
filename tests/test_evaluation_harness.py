from __future__ import annotations

import unittest

from git_archaeologist.evaluation.evaluation_harness import (
    AnswerEvaluation,
    FailureStage,
    RetrievalEvaluation,
    TargetResolutionEvaluation,
    build_evaluation_report,
)


class EvaluationHarnessTests(unittest.TestCase):
    def test_search_and_answer_metrics_are_reported_separately(self) -> None:
        report = build_evaluation_report(
            target_cases=(TargetResolutionEvaluation("case-1", "target-a", "target-a"),),
            retrieval_cases=(RetrievalEvaluation("case-1", ("ev-1", "ev-2"), ("ev-2", "ev-1")),),
            answer_cases=(
                AnswerEvaluation(
                    case_id="case-1",
                    expected_risk_label="risk_found",
                    predicted_risk_label="risk_found",
                    should_abstain=False,
                    abstained=False,
                    unsupported_claim_count=0,
                    citation_failure_count=0,
                ),
            ),
            k=2,
        )

        payload = report.to_dict()
        self.assertEqual(1.0, payload["search_metrics"]["target_resolution_accuracy"])
        self.assertEqual(1.0, payload["search_metrics"]["evidence_recall_at_k"])
        self.assertEqual(1.0, payload["answer_metrics"]["citation_consistency_rate"])
        self.assertEqual(1.0, payload["answer_metrics"]["risk_warning_precision"])

    def test_failures_are_classified_by_pipeline_stage(self) -> None:
        report = build_evaluation_report(
            target_cases=(TargetResolutionEvaluation("case-target", "expected", "other"),),
            retrieval_cases=(RetrievalEvaluation("case-search", ("ev-required",), ("ev-other",)),),
            answer_cases=(
                AnswerEvaluation(
                    case_id="case-answer",
                    expected_risk_label="no_risk_found",
                    predicted_risk_label="risk_found",
                    should_abstain=True,
                    abstained=False,
                    unsupported_claim_count=2,
                    citation_failure_count=1,
                ),
            ),
        )

        stages = {failure.stage for failure in report.failures}
        self.assertIn(FailureStage.TARGET_RESOLUTION, stages)
        self.assertIn(FailureStage.SEARCH, stages)
        self.assertIn(FailureStage.RERANK, stages)
        self.assertIn(FailureStage.GENERATION, stages)
        self.assertIn(FailureStage.CITATION_VERIFICATION, stages)

    def test_retrieval_recall_and_mrr_are_computed(self) -> None:
        case = RetrievalEvaluation("case-1", ("ev-2",), ("ev-1", "ev-2", "ev-3"))

        self.assertEqual(0.0, case.recall_at(1))
        self.assertEqual(1.0, case.recall_at(2))
        self.assertEqual(0.5, case.reciprocal_rank())

    def test_risk_warning_precision_penalizes_false_warnings(self) -> None:
        report = build_evaluation_report(
            target_cases=(),
            retrieval_cases=(),
            answer_cases=(
                AnswerEvaluation("true-positive", "risk_found", "risk_found", False, False, 0, 0),
                AnswerEvaluation("false-positive", "no_risk_found", "risk_found", False, False, 0, 0),
            ),
        )

        self.assertEqual(0.5, report.risk_warning_precision)


if __name__ == "__main__":
    unittest.main()
