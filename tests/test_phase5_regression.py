from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

from git_archaeologist.evaluation.phase5_regression import (
    PHASE5_REGRESSION_SUITE_ID,
    Phase5RegressionSection,
    Phase5RegressionStatus,
    build_phase5_regression_report,
    load_baseline_metrics,
    main,
    phase5_regression_report_to_dict,
    write_phase5_regression_report,
)


class Phase5RegressionTests(unittest.TestCase):
    def test_phase5_suite_reports_required_sections(self) -> None:
        report = build_phase5_regression_report(
            include_post_sft=False,
            measured_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )
        payload = phase5_regression_report_to_dict(report)

        self.assertEqual(PHASE5_REGRESSION_SUITE_ID, payload["suite_id"])
        self.assertEqual("passed", payload["status"])
        section_ids = {section["section_id"] for section in payload["sections"]}
        for expected in (
            Phase5RegressionSection.TARGET_RESOLUTION,
            Phase5RegressionSection.SEARCH,
            Phase5RegressionSection.ANSWER,
            Phase5RegressionSection.CITATION,
            Phase5RegressionSection.ABSTENTION,
            Phase5RegressionSection.INCIDENT,
            Phase5RegressionSection.LINEAGE,
            Phase5RegressionSection.PERFORMANCE,
        ):
            self.assertIn(expected.value, section_ids)
        self.assertIn("target_resolution.accuracy", payload["metrics"])
        self.assertIn("performance.max_p95_latency_ms", payload["metrics"])

    def test_baseline_regression_marks_suite_failed(self) -> None:
        report = build_phase5_regression_report(
            baseline_metrics={"performance.max_p95_latency_ms": 1.0},
            include_post_sft=False,
            measured_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        self.assertEqual(Phase5RegressionStatus.FAILED, report.status)
        regression = next(
            comparison
            for comparison in report.baseline_comparisons
            if comparison.metric_name == "performance.max_p95_latency_ms"
        )
        self.assertTrue(regression.regression_detected)

    def test_previous_report_can_be_loaded_as_baseline(self) -> None:
        report = build_phase5_regression_report(
            include_post_sft=False,
            measured_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, markdown_path = write_phase5_regression_report(
                report,
                output_dir=temp_dir,
            )
            baseline = load_baseline_metrics(json_path)

        self.assertTrue(json_path.name.endswith(".json"))
        self.assertTrue(markdown_path.name.endswith(".md"))
        self.assertEqual(1.0, baseline["target_resolution.accuracy"])
        self.assertAlmostEqual(50.0, baseline["performance.max_p95_latency_ms"])

    def test_cli_runs_named_suite_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--suite",
                        PHASE5_REGRESSION_SUITE_ID,
                        "--output-dir",
                        temp_dir,
                        "--skip-post-sft",
                    ]
                )
            payload = json.loads((Path(temp_dir) / "phase5-regression.json").read_text(encoding="utf-8"))

        self.assertEqual(0, exit_code)
        self.assertEqual("passed", payload["status"])
        self.assertEqual(PHASE5_REGRESSION_SUITE_ID, payload["suite_id"])


if __name__ == "__main__":
    unittest.main()
