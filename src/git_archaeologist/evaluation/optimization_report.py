"""Phase 5 model and index optimization comparison reports.

The report consumes structured, already-measured or deterministic mock results.
It does not train models, collect external data, or invoke heavy model runtimes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
from typing import Any

from git_archaeologist.evaluation.runtime_profile import (
    MVP_RUNTIME_PROFILE_ID,
    RUNTIME_PROFILE_VERSION,
    RuntimeOptimizationProfile,
    load_default_optimization_profiles,
    model_name_to_data_dir_name,
)


OPTIMIZATION_REPORT_VERSION = "phase5-optimization-report-v1"
DEFAULT_MAX_RESPONSE_P95_LATENCY_MS = 30_000.0


def _validate_rate(name: str, value: float) -> None:
    if value < 0 or value > 1:
        raise ValueError(f"{name} must be in the range [0, 1]")


@dataclass(frozen=True)
class QualityMetrics:
    """Quality metrics used to guard optimization recommendations."""

    evidence_recall_at_k: float
    citation_integrity_rate: float
    unsupported_claim_rate: float
    risk_precision: float
    schema_valid_rate: float

    def __post_init__(self) -> None:
        _validate_rate("evidence_recall_at_k", self.evidence_recall_at_k)
        _validate_rate("citation_integrity_rate", self.citation_integrity_rate)
        _validate_rate("unsupported_claim_rate", self.unsupported_claim_rate)
        _validate_rate("risk_precision", self.risk_precision)
        _validate_rate("schema_valid_rate", self.schema_valid_rate)


@dataclass(frozen=True)
class SpeedMetrics:
    """Latency, throughput, and resource metrics for one profile."""

    p95_latency_ms: float
    representative_latency_ms: float
    throughput_per_second: float | None
    peak_ram_bytes: int | None
    peak_vram_bytes: int | None

    def __post_init__(self) -> None:
        if self.p95_latency_ms <= 0:
            raise ValueError("p95_latency_ms must be positive")
        if self.representative_latency_ms <= 0:
            raise ValueError("representative_latency_ms must be positive")
        if (
            self.throughput_per_second is not None
            and self.throughput_per_second <= 0
        ):
            raise ValueError("throughput_per_second must be positive")
        if self.peak_ram_bytes is not None and self.peak_ram_bytes <= 0:
            raise ValueError("peak_ram_bytes must be positive")
        if self.peak_vram_bytes is not None and self.peak_vram_bytes < 0:
            raise ValueError("peak_vram_bytes must not be negative")


@dataclass(frozen=True)
class QualityThresholds:
    """Minimum quality bar a profile must satisfy before recommendation."""

    minimum_evidence_recall_at_k: float = 0.85
    minimum_citation_integrity_rate: float = 0.98
    maximum_unsupported_claim_rate: float = 0.02
    minimum_risk_precision: float = 0.80
    minimum_schema_valid_rate: float = 0.99

    def __post_init__(self) -> None:
        _validate_rate(
            "minimum_evidence_recall_at_k",
            self.minimum_evidence_recall_at_k,
        )
        _validate_rate(
            "minimum_citation_integrity_rate",
            self.minimum_citation_integrity_rate,
        )
        _validate_rate(
            "maximum_unsupported_claim_rate",
            self.maximum_unsupported_claim_rate,
        )
        _validate_rate("minimum_risk_precision", self.minimum_risk_precision)
        _validate_rate("minimum_schema_valid_rate", self.minimum_schema_valid_rate)


@dataclass(frozen=True)
class OptimizationRequirements:
    """Quality and speed gates for profile recommendation."""

    quality_thresholds: QualityThresholds = QualityThresholds()
    max_response_p95_latency_ms: float | None = DEFAULT_MAX_RESPONSE_P95_LATENCY_MS
    max_peak_ram_bytes: int | None = None

    def __post_init__(self) -> None:
        if (
            self.max_response_p95_latency_ms is not None
            and self.max_response_p95_latency_ms <= 0
        ):
            raise ValueError("max_response_p95_latency_ms must be positive")
        if self.max_peak_ram_bytes is not None and self.max_peak_ram_bytes <= 0:
            raise ValueError("max_peak_ram_bytes must be positive")


@dataclass(frozen=True)
class ProfileEvaluation:
    """Structured quality and speed result for one runtime profile."""

    profile: RuntimeOptimizationProfile
    quality: QualityMetrics
    speed: SpeedMetrics
    measured: bool
    measurement_source: str
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.measurement_source:
            raise ValueError("measurement_source must be non-empty")


@dataclass(frozen=True)
class ProfileDecision:
    """Recommendation or rejection decision for one profile."""

    profile_id: str
    eligible: bool
    recommended: bool
    quality_status: str
    speed_status: str
    quality_score: float
    quality_failures: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    recommendation_reason: str | None


@dataclass(frozen=True)
class RecommendedRuntimeProfile:
    """Recommended model/index settings copied into a small runtime payload."""

    profile_id: str
    model_id: str
    quantization: str
    max_context_tokens: int
    batch_size: int
    embedding_cache: str
    context_compression_ratio: float
    candidate_count: int
    rerank_top_k: int
    expected_p95_latency_ms: float
    expected_peak_ram_bytes: int | None
    reason: str


@dataclass(frozen=True)
class OptimizationReport:
    """Serializable Phase 5 optimization comparison report."""

    schema_version: str
    runtime_profile_version: str
    profile_id: str
    generated_at: str
    requirements: OptimizationRequirements
    evaluations: tuple[ProfileEvaluation, ...]
    decisions: tuple[ProfileDecision, ...]
    recommended_runtime_profile: RecommendedRuntimeProfile | None
    notes: tuple[str, ...] = ()


def build_optimization_report(
    evaluations: tuple[ProfileEvaluation, ...],
    *,
    requirements: OptimizationRequirements | None = None,
    generated_at: datetime | None = None,
) -> OptimizationReport:
    """Build a quality-guarded speed comparison report."""

    if not evaluations:
        raise ValueError("evaluations must not be empty")
    profile_ids = [evaluation.profile.profile_id for evaluation in evaluations]
    if len(set(profile_ids)) != len(profile_ids):
        raise ValueError("profile_id values must be unique")

    active_requirements = requirements or OptimizationRequirements()
    timestamp = generated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("generated_at must include a timezone")

    preliminary_decisions = tuple(
        evaluate_profile(evaluation, active_requirements)
        for evaluation in evaluations
    )
    recommended = _select_recommended_profile(evaluations, preliminary_decisions)
    decisions = _finalize_decisions(preliminary_decisions, recommended)

    return OptimizationReport(
        schema_version=OPTIMIZATION_REPORT_VERSION,
        runtime_profile_version=RUNTIME_PROFILE_VERSION,
        profile_id=MVP_RUNTIME_PROFILE_ID,
        generated_at=timestamp.astimezone(timezone.utc).isoformat(),
        requirements=active_requirements,
        evaluations=evaluations,
        decisions=decisions,
        recommended_runtime_profile=recommended,
        notes=(
            "Recommendations require measured or deterministic test results; unmeasured profiles are rejected.",
            "This report consumes structured inputs and does not run model training or heavy model inference.",
        ),
    )


def evaluate_profile(
    evaluation: ProfileEvaluation,
    requirements: OptimizationRequirements,
) -> ProfileDecision:
    """Return the recommendation decision for one profile."""

    quality_failures = evaluate_quality(evaluation.quality, requirements.quality_thresholds)
    speed_failures = evaluate_speed(evaluation.speed, requirements)
    rejection_reasons: list[str] = []
    if not evaluation.measured:
        rejection_reasons.append(
            "Profile has no measured or deterministic test result and cannot be recommended."
        )
    rejection_reasons.extend(quality_failures)
    rejection_reasons.extend(speed_failures)

    quality_status = "passed" if not quality_failures else "failed"
    speed_status = "passed" if not speed_failures else "failed"
    quality_score = score_quality(evaluation.quality)
    eligible = not rejection_reasons
    recommendation_reason = None
    if eligible:
        recommendation_reason = (
            "Profile satisfies all quality thresholds and speed/resource targets; "
            f"p95 latency is {evaluation.speed.p95_latency_ms:.2f} ms."
        )

    return ProfileDecision(
        profile_id=evaluation.profile.profile_id,
        eligible=eligible,
        recommended=False,
        quality_status=quality_status,
        speed_status=speed_status,
        quality_score=quality_score,
        quality_failures=quality_failures,
        rejection_reasons=tuple(rejection_reasons),
        recommendation_reason=recommendation_reason,
    )


def evaluate_quality(
    quality: QualityMetrics,
    thresholds: QualityThresholds,
) -> tuple[str, ...]:
    """Return quality threshold failures."""

    failures: list[str] = []
    if quality.evidence_recall_at_k < thresholds.minimum_evidence_recall_at_k:
        failures.append(
            "evidence_recall_at_k below threshold: "
            f"{quality.evidence_recall_at_k:.3f} < "
            f"{thresholds.minimum_evidence_recall_at_k:.3f}"
        )
    if quality.citation_integrity_rate < thresholds.minimum_citation_integrity_rate:
        failures.append(
            "citation_integrity_rate below threshold: "
            f"{quality.citation_integrity_rate:.3f} < "
            f"{thresholds.minimum_citation_integrity_rate:.3f}"
        )
    if quality.unsupported_claim_rate > thresholds.maximum_unsupported_claim_rate:
        failures.append(
            "unsupported_claim_rate above threshold: "
            f"{quality.unsupported_claim_rate:.3f} > "
            f"{thresholds.maximum_unsupported_claim_rate:.3f}"
        )
    if quality.risk_precision < thresholds.minimum_risk_precision:
        failures.append(
            "risk_precision below threshold: "
            f"{quality.risk_precision:.3f} < "
            f"{thresholds.minimum_risk_precision:.3f}"
        )
    if quality.schema_valid_rate < thresholds.minimum_schema_valid_rate:
        failures.append(
            "schema_valid_rate below threshold: "
            f"{quality.schema_valid_rate:.3f} < "
            f"{thresholds.minimum_schema_valid_rate:.3f}"
        )
    return tuple(failures)


def evaluate_speed(
    speed: SpeedMetrics,
    requirements: OptimizationRequirements,
) -> tuple[str, ...]:
    """Return speed/resource target failures."""

    failures: list[str] = []
    if (
        requirements.max_response_p95_latency_ms is not None
        and speed.p95_latency_ms > requirements.max_response_p95_latency_ms
    ):
        failures.append(
            "p95_latency_ms above target: "
            f"{speed.p95_latency_ms:.2f} > "
            f"{requirements.max_response_p95_latency_ms:.2f}"
        )
    if (
        requirements.max_peak_ram_bytes is not None
        and speed.peak_ram_bytes is not None
        and speed.peak_ram_bytes > requirements.max_peak_ram_bytes
    ):
        failures.append(
            "peak_ram_bytes above target: "
            f"{speed.peak_ram_bytes} > {requirements.max_peak_ram_bytes}"
        )
    return tuple(failures)


def score_quality(quality: QualityMetrics) -> float:
    """Return a stable composite quality score for tie-breaking."""

    supported_claim_score = 1.0 - quality.unsupported_claim_rate
    return (
        quality.evidence_recall_at_k
        + quality.citation_integrity_rate
        + supported_claim_score
        + quality.risk_precision
        + quality.schema_valid_rate
    ) / 5.0


def optimization_report_to_dict(report: OptimizationReport) -> dict[str, Any]:
    """Return a JSON-friendly optimization report."""

    return asdict(report)


def optimization_report_to_json(report: OptimizationReport) -> str:
    """Return formatted JSON for a Phase 5 optimization report."""

    return json.dumps(optimization_report_to_dict(report), ensure_ascii=False, indent=2)


def optimization_report_summary_to_markdown(report: OptimizationReport) -> str:
    """Return a short human-readable comparison summary."""

    recommended = report.recommended_runtime_profile
    lines = [
        "# Phase 5 Optimization Report",
        "",
        f"- Schema: `{report.schema_version}`",
        f"- Runtime profile: `{report.profile_id}` / `{report.runtime_profile_version}`",
        f"- Generated at: `{report.generated_at}`",
        f"- Recommended profile: `{recommended.profile_id if recommended else 'none'}`",
        "",
        "| Profile | Measured | Quality | Speed | p95 ms | Decision |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    decisions_by_profile = {decision.profile_id: decision for decision in report.decisions}
    for evaluation in report.evaluations:
        decision = decisions_by_profile[evaluation.profile.profile_id]
        decision_text = "recommended" if decision.recommended else "rejected"
        lines.append(
            "| "
            f"{evaluation.profile.profile_id} | "
            f"{str(evaluation.measured).lower()} | "
            f"{decision.quality_status} | "
            f"{decision.speed_status} | "
            f"{evaluation.speed.p95_latency_ms:.2f} | "
            f"{decision_text} |"
        )
    lines.extend(["", "## Decisions", ""])
    for decision in report.decisions:
        if decision.recommended and decision.recommendation_reason:
            lines.append(f"- `{decision.profile_id}`: {decision.recommendation_reason}")
        else:
            reasons = "; ".join(decision.rejection_reasons)
            lines.append(f"- `{decision.profile_id}` rejected: {reasons}")
    return "\n".join(lines) + "\n"


def write_optimization_report(
    report: OptimizationReport,
    *,
    output_dir: str | Path,
    json_filename: str = "optimization-report.json",
    markdown_filename: str = "optimization-report.md",
) -> tuple[Path, Path]:
    """Write report JSON and summary markdown under output_dir."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / json_filename
    markdown_path = root / markdown_filename
    json_path.write_text(optimization_report_to_json(report) + "\n", encoding="utf-8")
    markdown_path.write_text(
        optimization_report_summary_to_markdown(report),
        encoding="utf-8",
    )
    return json_path, markdown_path


def default_optimization_output_dir(
    *,
    data_root: str | Path = "data",
    model_name: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
) -> Path:
    """Return the conventional model run directory for optimization reports."""

    model_dir = model_name_to_data_dir_name(model_name)
    return Path(data_root) / model_dir / "runs" / "optimization-report"


def _select_recommended_profile(
    evaluations: tuple[ProfileEvaluation, ...],
    decisions: tuple[ProfileDecision, ...],
) -> RecommendedRuntimeProfile | None:
    decisions_by_profile = {decision.profile_id: decision for decision in decisions}
    eligible = [
        evaluation
        for evaluation in evaluations
        if decisions_by_profile[evaluation.profile.profile_id].eligible
    ]
    if not eligible:
        return None

    selected = min(
        eligible,
        key=lambda evaluation: (
            evaluation.speed.p95_latency_ms,
            evaluation.speed.peak_ram_bytes
            if evaluation.speed.peak_ram_bytes is not None
            else float("inf"),
            -score_quality(evaluation.quality),
        ),
    )
    decision = decisions_by_profile[selected.profile.profile_id]
    reason = decision.recommendation_reason or "Profile passed all gates."
    return RecommendedRuntimeProfile(
        profile_id=selected.profile.profile_id,
        model_id=selected.profile.model_id,
        quantization=selected.profile.quantization,
        max_context_tokens=selected.profile.max_context_tokens,
        batch_size=selected.profile.batch_size,
        embedding_cache=selected.profile.index.embedding_cache,
        context_compression_ratio=selected.profile.index.context_compression_ratio,
        candidate_count=selected.profile.index.candidate_count,
        rerank_top_k=selected.profile.index.rerank_top_k,
        expected_p95_latency_ms=selected.speed.p95_latency_ms,
        expected_peak_ram_bytes=selected.speed.peak_ram_bytes,
        reason=reason,
    )


def _finalize_decisions(
    decisions: tuple[ProfileDecision, ...],
    recommended: RecommendedRuntimeProfile | None,
) -> tuple[ProfileDecision, ...]:
    if recommended is None:
        return decisions

    finalized: list[ProfileDecision] = []
    for decision in decisions:
        if decision.profile_id == recommended.profile_id:
            finalized.append(
                replace(
                    decision,
                    recommended=True,
                    rejection_reasons=(),
                    recommendation_reason=recommended.reason,
                )
            )
            continue
        if decision.eligible:
            finalized.append(
                replace(
                    decision,
                    rejection_reasons=(
                        "Profile passed all gates but was not selected because "
                        f"{recommended.profile_id} had the best speed/resource "
                        "tie-break among eligible profiles.",
                    ),
                    recommendation_reason=None,
                )
            )
            continue
        finalized.append(decision)
    return tuple(finalized)


def _build_default_evaluations() -> tuple[ProfileEvaluation, ...]:
    profiles = load_default_optimization_profiles()
    return (
        ProfileEvaluation(
            profile=profiles[0],
            quality=QualityMetrics(
                evidence_recall_at_k=0.91,
                citation_integrity_rate=0.99,
                unsupported_claim_rate=0.01,
                risk_precision=0.86,
                schema_valid_rate=1.0,
            ),
            speed=SpeedMetrics(
                p95_latency_ms=28_000.0,
                representative_latency_ms=22_000.0,
                throughput_per_second=8.2,
                peak_ram_bytes=15 * 1024**3,
                peak_vram_bytes=None,
            ),
            measured=True,
            measurement_source="deterministic-default-fixture",
            notes=("Baseline deterministic comparison row.",),
        ),
        ProfileEvaluation(
            profile=profiles[1],
            quality=QualityMetrics(
                evidence_recall_at_k=0.89,
                citation_integrity_rate=0.99,
                unsupported_claim_rate=0.012,
                risk_precision=0.84,
                schema_valid_rate=1.0,
            ),
            speed=SpeedMetrics(
                p95_latency_ms=18_000.0,
                representative_latency_ms=14_000.0,
                throughput_per_second=10.5,
                peak_ram_bytes=13 * 1024**3,
                peak_vram_bytes=None,
            ),
            measured=True,
            measurement_source="deterministic-default-fixture",
            notes=("Moderate compression preserves quality in the fixture.",),
        ),
        ProfileEvaluation(
            profile=profiles[2],
            quality=QualityMetrics(
                evidence_recall_at_k=0.78,
                citation_integrity_rate=0.97,
                unsupported_claim_rate=0.03,
                risk_precision=0.76,
                schema_valid_rate=1.0,
            ),
            speed=SpeedMetrics(
                p95_latency_ms=11_000.0,
                representative_latency_ms=9_000.0,
                throughput_per_second=14.0,
                peak_ram_bytes=11 * 1024**3,
                peak_vram_bytes=None,
            ),
            measured=True,
            measurement_source="deterministic-default-fixture",
            notes=("Fast profile intentionally falls below quality gates.",),
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(default_optimization_output_dir()),
        help="Directory for optimization-report.json and optimization-report.md.",
    )
    args = parser.parse_args(argv)

    report = build_optimization_report(_build_default_evaluations())
    json_path, markdown_path = write_optimization_report(
        report,
        output_dir=args.output_dir,
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
