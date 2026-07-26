from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from git_archaeologist.evaluation.phase5_performance import (
    ChatPerformanceCase,
    DEFAULT_PERFORMANCE_STAGES,
    UnknownResourceSampler,
    build_phase5_performance_report,
    default_phase5_output_dir,
    phase5_performance_report_to_dict,
    phase5_performance_summary_to_markdown,
    write_phase5_performance_report,
)
from git_archaeologist.ops.query_trace import ResourceReading


class FakeClock:
    def __init__(self, durations: tuple[float, ...]) -> None:
        self._durations = durations
        self._current = 100.0
        self._call_index = 0

    def __call__(self) -> float:
        stage_index = self._call_index // 2
        is_finish_call = self._call_index % 2 == 1
        self._call_index += 1
        if is_finish_call:
            self._current += self._durations[stage_index]
        return self._current


class CountingResourceSampler:
    def __init__(self) -> None:
        self._sample_count = 0

    def sample(self) -> ResourceReading:
        self._sample_count += 1
        return ResourceReading(
            cpu_seconds=self._sample_count * 0.01,
            ram_bytes=200_000_000 + self._sample_count,
            gpu_utilization_percent=12.5,
            vram_bytes=500_000_000 + self._sample_count,
            notes=("deterministic resource sample",),
        )


class Phase5PerformanceTests(unittest.TestCase):
    def test_deterministic_backend_records_stage_latency_in_query_trace(self) -> None:
        cases = (
            ChatPerformanceCase(
                case_id="case-1",
                raw_input="https://github.com/example/repo/pull/1 src/app.py の理由",
            ),
            ChatPerformanceCase(
                case_id="case-2",
                raw_input="https://github.com/example/repo/pull/2 src/app.py のリスク",
            ),
        )
        durations = (
            0.01,
            0.02,
            0.03,
            0.50,
            0.04,
            0.02,
            0.03,
            0.04,
            0.60,
            0.05,
        )

        report = build_phase5_performance_report(
            cases,
            resource_sampler=CountingResourceSampler(),
            clock=FakeClock(durations),
            measured_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )
        payload = phase5_performance_report_to_dict(report)

        self.assertEqual("phase5-chat-performance-v1", payload["schema_version"])
        self.assertEqual(2, payload["case_count"])
        self.assertEqual(DEFAULT_PERFORMANCE_STAGES, report.stages)
        self.assertEqual(10, len(report.stage_records))
        self.assertEqual("answer_generation", report.bottleneck.stage)
        self.assertAlmostEqual(600.0, report.bottleneck.p95_latency_ms)
        self.assertEqual(2, len(report.traces))
        self.assertEqual(DEFAULT_PERFORMANCE_STAGES, tuple(step.name for step in report.traces[0].steps))
        self.assertTrue(
            all("performance" in step.payload for trace in report.traces for step in trace.steps)
        )

        answer_record = next(
            record
            for record in report.stage_records
            if record.case_id == "case-1" and record.stage == "answer_generation"
        )
        self.assertAlmostEqual(500.0, answer_record.latency_ms)
        self.assertEqual("measured", answer_record.resource_status)
        self.assertIsNotNone(answer_record.cpu_seconds_delta)

    def test_unknown_resource_sampler_keeps_report_safe(self) -> None:
        report = build_phase5_performance_report(
            (
                ChatPerformanceCase(
                    case_id="case-unknown",
                    raw_input="https://github.com/example/repo/pull/3 src/app.py",
                ),
            ),
            resource_sampler=UnknownResourceSampler(),
            clock=FakeClock((0.01, 0.02, 0.03, 0.08, 0.05)),
            measured_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        self.assertEqual("answer_generation", report.bottleneck.stage)
        self.assertTrue(
            all(record.resource_status == "unknown" for record in report.stage_records)
        )
        self.assertTrue(all(record.ram_bytes is None for record in report.stage_records))
        self.assertTrue(all(record.vram_bytes is None for record in report.stage_records))

    def test_report_json_and_summary_markdown_are_written(self) -> None:
        report = build_phase5_performance_report(
            (
                ChatPerformanceCase(
                    case_id="case-write",
                    raw_input="https://github.com/example/repo/pull/4 src/app.py",
                ),
            ),
            resource_sampler=UnknownResourceSampler(),
            clock=FakeClock((0.01, 0.02, 0.03, 0.04, 0.05)),
            measured_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, markdown_path = write_phase5_performance_report(
                report,
                output_dir=temp_dir,
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            summary = markdown_path.read_text(encoding="utf-8")

        self.assertEqual("phase5-chat-performance-v1", payload["schema_version"])
        self.assertIn("Phase 5 Chat E2E Performance", summary)
        self.assertIn("answer_generation", summary)

    def test_default_output_dir_uses_model_run_directory(self) -> None:
        self.assertEqual(
            Path("data")
            / "Qwen--Qwen2.5-Coder-7B-Instruct"
            / "runs"
            / "phase5-performance",
            default_phase5_output_dir(),
        )

    def test_rejects_naive_measurement_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "measured_at must include a timezone"):
            build_phase5_performance_report(
                (
                    ChatPerformanceCase(
                        case_id="case-naive",
                        raw_input="https://github.com/example/repo/pull/5 src/app.py",
                    ),
                ),
                measured_at=datetime(2026, 7, 26),
            )

    def test_summary_markdown_explains_bottleneck(self) -> None:
        report = build_phase5_performance_report(
            (
                ChatPerformanceCase(
                    case_id="case-summary",
                    raw_input="https://github.com/example/repo/pull/6 src/app.py",
                ),
            ),
            resource_sampler=UnknownResourceSampler(),
            clock=FakeClock((0.01, 0.02, 0.03, 0.80, 0.05)),
            measured_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        summary = phase5_performance_summary_to_markdown(report)

        self.assertIn("Bottleneck", summary)
        self.assertIn("answer_generation has the highest p95 latency", summary)


if __name__ == "__main__":
    unittest.main()
