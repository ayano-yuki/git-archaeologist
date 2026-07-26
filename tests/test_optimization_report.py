from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from git_archaeologist.evaluation.optimization_report import (
    QualityMetrics,
    SpeedMetrics,
    ProfileEvaluation,
    build_optimization_report,
    default_optimization_output_dir,
    optimization_report_to_dict,
    optimization_report_to_json,
    optimization_report_summary_to_markdown,
    write_optimization_report,
)
from git_archaeologist.evaluation.runtime_profile import (
    RUNTIME_PROFILE_VERSION,
    load_default_optimization_profiles,
)


def _quality(
    *,
    evidence_recall_at_k: float = 0.90,
    citation_integrity_rate: float = 0.99,
    unsupported_claim_rate: float = 0.01,
    risk_precision: float = 0.85,
    schema_valid_rate: float = 1.0,
) -> QualityMetrics:
    return QualityMetrics(
        evidence_recall_at_k=evidence_recall_at_k,
        citation_integrity_rate=citation_integrity_rate,
        unsupported_claim_rate=unsupported_claim_rate,
        risk_precision=risk_precision,
        schema_valid_rate=schema_valid_rate,
    )


def _speed(
    *,
    p95_latency_ms: float,
    peak_ram_bytes: int = 12 * 1024**3,
) -> SpeedMetrics:
    return SpeedMetrics(
        p95_latency_ms=p95_latency_ms,
        representative_latency_ms=p95_latency_ms * 0.75,
        throughput_per_second=10.0,
        peak_ram_bytes=peak_ram_bytes,
        peak_vram_bytes=None,
    )


class OptimizationReportTests(unittest.TestCase):
    def test_recommends_fastest_measured_profile_that_preserves_quality(self) -> None:
        baseline, cache_profile, fast_profile = load_default_optimization_profiles()
        report = build_optimization_report(
            (
                ProfileEvaluation(
                    profile=baseline,
                    quality=_quality(),
                    speed=_speed(p95_latency_ms=28_000.0),
                    measured=True,
                    measurement_source="deterministic-test",
                ),
                ProfileEvaluation(
                    profile=cache_profile,
                    quality=_quality(evidence_recall_at_k=0.88, risk_precision=0.82),
                    speed=_speed(p95_latency_ms=16_000.0),
                    measured=True,
                    measurement_source="deterministic-test",
                ),
                ProfileEvaluation(
                    profile=fast_profile,
                    quality=_quality(
                        evidence_recall_at_k=0.74,
                        citation_integrity_rate=0.97,
                        unsupported_claim_rate=0.04,
                        risk_precision=0.70,
                    ),
                    speed=_speed(p95_latency_ms=8_000.0),
                    measured=True,
                    measurement_source="deterministic-test",
                ),
            ),
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(report.recommended_runtime_profile)
        self.assertEqual(
            "cache-compressed-context",
            report.recommended_runtime_profile.profile_id,
        )
        decisions = {decision.profile_id: decision for decision in report.decisions}
        self.assertTrue(decisions["baseline-qwen-4bit-full-context"].eligible)
        self.assertFalse(decisions["baseline-qwen-4bit-full-context"].recommended)
        self.assertTrue(decisions["cache-compressed-context"].recommended)
        self.assertFalse(decisions["fast-small-candidate-set"].recommended)
        self.assertIn(
            "not selected",
            "; ".join(decisions["baseline-qwen-4bit-full-context"].rejection_reasons),
        )
        self.assertIn(
            "evidence_recall_at_k below threshold",
            "; ".join(decisions["fast-small-candidate-set"].rejection_reasons),
        )

    def test_unmeasured_profile_is_never_recommended(self) -> None:
        baseline, cache_profile, _ = load_default_optimization_profiles()
        report = build_optimization_report(
            (
                ProfileEvaluation(
                    profile=baseline,
                    quality=_quality(),
                    speed=_speed(p95_latency_ms=21_000.0),
                    measured=True,
                    measurement_source="deterministic-test",
                ),
                ProfileEvaluation(
                    profile=cache_profile,
                    quality=_quality(),
                    speed=_speed(p95_latency_ms=3_000.0),
                    measured=False,
                    measurement_source="not-measured",
                ),
            ),
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(report.recommended_runtime_profile)
        self.assertEqual(
            "baseline-qwen-4bit-full-context",
            report.recommended_runtime_profile.profile_id,
        )
        rejected = next(
            decision
            for decision in report.decisions
            if decision.profile_id == "cache-compressed-context"
        )
        self.assertFalse(rejected.recommended)
        self.assertIn("no measured", "; ".join(rejected.rejection_reasons))

    def test_report_is_json_serializable_with_recommendation_reasons(self) -> None:
        profile = load_default_optimization_profiles()[0]
        report = build_optimization_report(
            (
                ProfileEvaluation(
                    profile=profile,
                    quality=_quality(),
                    speed=_speed(p95_latency_ms=20_000.0),
                    measured=True,
                    measurement_source="deterministic-test",
                ),
            ),
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )
        payload = optimization_report_to_dict(report)
        serialized = optimization_report_to_json(report)

        self.assertEqual("phase5-optimization-report-v1", payload["schema_version"])
        self.assertEqual(RUNTIME_PROFILE_VERSION, payload["runtime_profile_version"])
        self.assertEqual(
            "baseline-qwen-4bit-full-context",
            payload["recommended_runtime_profile"]["profile_id"],
        )
        self.assertIn("recommendation_reason", serialized)

    def test_all_profiles_can_be_rejected_without_recommendation(self) -> None:
        profile = load_default_optimization_profiles()[0]
        report = build_optimization_report(
            (
                ProfileEvaluation(
                    profile=profile,
                    quality=_quality(evidence_recall_at_k=0.80),
                    speed=_speed(p95_latency_ms=20_000.0),
                    measured=True,
                    measurement_source="deterministic-test",
                ),
            ),
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        self.assertIsNone(report.recommended_runtime_profile)
        self.assertFalse(report.decisions[0].recommended)
        self.assertEqual("failed", report.decisions[0].quality_status)

    def test_writes_json_and_summary_markdown(self) -> None:
        profile = load_default_optimization_profiles()[0]
        report = build_optimization_report(
            (
                ProfileEvaluation(
                    profile=profile,
                    quality=_quality(),
                    speed=_speed(p95_latency_ms=20_000.0),
                    measured=True,
                    measurement_source="deterministic-test",
                ),
            ),
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, markdown_path = write_optimization_report(
                report,
                output_dir=temp_dir,
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            summary = markdown_path.read_text(encoding="utf-8")

        self.assertEqual("phase5-optimization-report-v1", payload["schema_version"])
        self.assertIn("Phase 5 Optimization Report", summary)
        self.assertIn("baseline-qwen-4bit-full-context", summary)

    def test_default_output_dir_uses_model_run_directory(self) -> None:
        self.assertEqual(
            Path("data")
            / "Qwen--Qwen2.5-Coder-7B-Instruct"
            / "runs"
            / "optimization-report",
            default_optimization_output_dir(),
        )

    def test_rejects_naive_generated_timestamp(self) -> None:
        profile = load_default_optimization_profiles()[0]
        with self.assertRaisesRegex(ValueError, "generated_at must include a timezone"):
            build_optimization_report(
                (
                    ProfileEvaluation(
                        profile=profile,
                        quality=_quality(),
                        speed=_speed(p95_latency_ms=20_000.0),
                        measured=True,
                        measurement_source="deterministic-test",
                    ),
                ),
                generated_at=datetime(2026, 7, 26),
            )

    def test_summary_markdown_records_rejection_reasons(self) -> None:
        profile = load_default_optimization_profiles()[0]
        report = build_optimization_report(
            (
                ProfileEvaluation(
                    profile=profile,
                    quality=_quality(evidence_recall_at_k=0.70),
                    speed=_speed(p95_latency_ms=20_000.0),
                    measured=True,
                    measurement_source="deterministic-test",
                ),
            ),
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        summary = optimization_report_summary_to_markdown(report)

        self.assertIn("rejected", summary)
        self.assertIn("evidence_recall_at_k below threshold", summary)


if __name__ == "__main__":
    unittest.main()
