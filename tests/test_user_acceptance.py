from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

from git_archaeologist.evaluation.user_acceptance import (
    AcceptanceDimension,
    HumanEvaluationRecord,
    ReleaseDecision,
    UnresolvedIssueSeverity,
    build_user_acceptance_report,
    default_user_acceptance_output_dir,
    extract_unresolved_issues,
    load_human_evaluation_records,
    load_user_acceptance_form,
    main,
    user_acceptance_report_to_dict,
    user_acceptance_summary_to_markdown,
    write_user_acceptance_report,
)


DATA_DIR = Path("data/baseline-rag/eval/user-acceptance")
FORM_PATH = DATA_DIR / "user-acceptance-form.json"
RECORDS_PATH = DATA_DIR / "sample-evaluations.jsonl"


class UserAcceptanceTests(unittest.TestCase):
    def test_fixture_form_records_required_rubric_and_thresholds(self) -> None:
        form = load_user_acceptance_form(FORM_PATH)

        rubric_dimensions = {item.dimension for item in form.rubric}
        self.assertEqual(set(AcceptanceDimension), rubric_dimensions)
        self.assertEqual(0, form.thresholds.maximum_critical_misinformation)
        self.assertLessEqual(form.thresholds.maximum_unnecessary_warning_rate, 0.20)
        self.assertIn(AcceptanceDimension.ACCURACY, form.thresholds.minimum_dimension_average)
        self.assertGreaterEqual(len(form.cases), 3)

    def test_report_builder_summarizes_human_scores_and_comments(self) -> None:
        form = load_user_acceptance_form(FORM_PATH)
        records = load_human_evaluation_records(RECORDS_PATH)

        report = build_user_acceptance_report(
            form,
            records,
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )
        payload = user_acceptance_report_to_dict(report)

        self.assertEqual("phase5-user-acceptance-report-v1", payload["schema_version"])
        self.assertEqual("needs_follow_up", payload["release_decision"])
        self.assertEqual(len(records), payload["record_count"])
        self.assertGreaterEqual(payload["average_scores"]["accuracy"], 4.0)
        self.assertGreaterEqual(payload["average_scores"]["evidence_sufficiency"], 4.0)
        threshold_ids = {item["threshold_id"] for item in payload["threshold_results"]}
        self.assertIn("maximum_critical_misinformation", threshold_ids)
        self.assertIn("maximum_unnecessary_warning_rate", threshold_ids)
        self.assertEqual(1, len(payload["unresolved_issues"]))
        self.assertEqual("warning", payload["unresolved_issues"][0]["severity"])

    def test_blocking_threshold_failure_blocks_release(self) -> None:
        form = load_user_acceptance_form(FORM_PATH)
        base = load_human_evaluation_records(RECORDS_PATH)[0]
        failing = HumanEvaluationRecord(
            record_id="ua-failing",
            case_id=base.case_id,
            evaluator_id="evaluator-gamma",
            evaluated_at="2026-07-26T00:00:00+00:00",
            scores=base.scores,
            warning_count=1,
            unnecessary_warning_count=0,
            critical_misinformation_count=1,
            investigation_minutes_without_tool=30.0,
            investigation_minutes_with_tool=20.0,
            comments="No unresolved follow-up.",
        )

        report = build_user_acceptance_report(
            form,
            (failing,),
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        self.assertEqual(ReleaseDecision.BLOCKED, report.release_decision)
        critical = next(
            result
            for result in report.threshold_results
            if result.threshold_id == "maximum_critical_misinformation"
        )
        self.assertFalse(critical.passed)

    def test_comment_markers_are_extracted_deterministically(self) -> None:
        record = load_human_evaluation_records(RECORDS_PATH)[1]

        issues = extract_unresolved_issues((record,))

        self.assertEqual(1, len(issues))
        self.assertEqual(UnresolvedIssueSeverity.WARNING, issues[0].severity)
        self.assertIn("false positive warning", issues[0].text)

    def test_report_writes_json_and_markdown(self) -> None:
        form = load_user_acceptance_form(FORM_PATH)
        records = load_human_evaluation_records(RECORDS_PATH)
        report = build_user_acceptance_report(
            form,
            records,
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, markdown_path = write_user_acceptance_report(
                report,
                output_dir=temp_dir,
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            summary = markdown_path.read_text(encoding="utf-8")

        self.assertEqual("needs_follow_up", payload["release_decision"])
        self.assertIn("Phase 5 User Acceptance", summary)
        self.assertIn("maximum_unnecessary_warning_rate", summary)

    def test_cli_uses_checked_in_fixture_without_writing_when_requested(self) -> None:
        with redirect_stdout(io.StringIO()) as buffer:
            exit_code = main(["--form", str(FORM_PATH), "--records", str(RECORDS_PATH), "--no-write"])
        payload = json.loads(buffer.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual("needs_follow_up", payload["release_decision"])

    def test_default_output_dir_matches_baseline_rag_eval_bucket(self) -> None:
        self.assertEqual(DATA_DIR, default_user_acceptance_output_dir())

    def test_rejects_naive_generated_timestamp(self) -> None:
        form = load_user_acceptance_form(FORM_PATH)
        records = load_human_evaluation_records(RECORDS_PATH)

        with self.assertRaisesRegex(ValueError, "generated_at must include a timezone"):
            build_user_acceptance_report(
                form,
                records,
                generated_at=datetime(2026, 7, 26),
            )

    def test_rejects_score_outside_form_rubric_range(self) -> None:
        form = load_user_acceptance_form(FORM_PATH)
        base = load_human_evaluation_records(RECORDS_PATH)[0]
        invalid = HumanEvaluationRecord(
            record_id="ua-invalid-score",
            case_id=base.case_id,
            evaluator_id="evaluator-gamma",
            evaluated_at="2026-07-26T00:00:00+00:00",
            scores={**base.scores, AcceptanceDimension.ACCURACY: 6.0},
            warning_count=0,
            unnecessary_warning_count=0,
            critical_misinformation_count=0,
            investigation_minutes_without_tool=30.0,
            investigation_minutes_with_tool=20.0,
            comments="No unresolved follow-up.",
        )

        with self.assertRaisesRegex(ValueError, "outside rubric range"):
            build_user_acceptance_report(
                form,
                (invalid,),
                generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            )

    def test_summary_includes_unresolved_issue_section(self) -> None:
        form = load_user_acceptance_form(FORM_PATH)
        records = load_human_evaluation_records(RECORDS_PATH)
        report = build_user_acceptance_report(
            form,
            records,
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        summary = user_acceptance_summary_to_markdown(report)

        self.assertIn("Unresolved Issues", summary)
        self.assertIn("false positive warning", summary)


if __name__ == "__main__":
    unittest.main()
