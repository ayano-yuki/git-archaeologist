"""Phase 5 full-function regression suite CLI.

The suite orchestrates existing deterministic checks. It does not train models,
collect external artifacts, or require heavy inference by default.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Mapping, Sequence

from git_archaeologist.evaluation.evaluation_harness import (
    AnswerEvaluation,
    EvaluationReport,
    FailureClassification,
    FailureStage,
    RetrievalEvaluation,
    TargetResolutionEvaluation,
    build_evaluation_report,
)
from git_archaeologist.evaluation.phase5_performance import (
    ChatPerformanceCase,
    Phase5PerformanceReport,
    UnknownResourceSampler,
    build_phase5_performance_report,
    phase5_performance_report_to_dict,
)
from git_archaeologist.evaluation.post_sft_evaluation import (
    PostSFTEvaluationReport,
    build_post_sft_evaluation_report,
    post_sft_evaluation_report_to_dict,
)
from git_archaeologist.evaluation.runtime_profile import model_name_to_data_dir_name
from git_archaeologist.ops.smoke import run_incident_smoke, run_lineage_smoke


PHASE5_REGRESSION_SUITE_ID = "phase5-regression-suite-v1"
PHASE5_REGRESSION_SCHEMA_VERSION = "phase5-regression-report-v1"


class Phase5RegressionSection(StrEnum):
    """Report sections required by the Phase 5 regression suite."""

    TARGET_RESOLUTION = "target_resolution"
    SEARCH = "search"
    ANSWER = "answer"
    RISK = "risk"
    CITATION = "citation"
    ABSTENTION = "abstention"
    INCIDENT = "incident"
    LINEAGE = "lineage"
    PERFORMANCE = "performance"
    POST_SFT = "post_sft"


class Phase5RegressionStatus(StrEnum):
    """Pass/fail state for a suite or section."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class MetricDirection(StrEnum):
    """How a metric should move relative to a baseline."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


@dataclass(frozen=True)
class BaselineComparison:
    """One metric comparison against a previous baseline."""

    metric_name: str
    current_value: float
    baseline_value: float
    delta: float
    direction: MetricDirection
    regression_detected: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["direction"] = self.direction.value
        return payload


@dataclass(frozen=True)
class Phase5RegressionSectionResult:
    """One isolated suite section with its own metrics and failures."""

    section_id: Phase5RegressionSection
    status: Phase5RegressionStatus
    required: bool
    metrics: dict[str, float]
    failures: tuple[dict[str, object], ...] = ()
    details: dict[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "failures", tuple(self.failures))

    def to_dict(self) -> dict[str, object]:
        return {
            "section_id": self.section_id.value,
            "status": self.status.value,
            "required": self.required,
            "metrics": dict(self.metrics),
            "failures": [dict(failure) for failure in self.failures],
            "details": dict(self.details or {}),
        }


@dataclass(frozen=True)
class Phase5RegressionReport:
    """Serializable Phase 5 regression suite result."""

    schema_version: str
    suite_id: str
    status: Phase5RegressionStatus
    measured_at: str
    sections: tuple[Phase5RegressionSectionResult, ...]
    metrics: dict[str, float]
    baseline_comparisons: tuple[BaselineComparison, ...]
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "sections", tuple(self.sections))
        object.__setattr__(self, "baseline_comparisons", tuple(self.baseline_comparisons))
        object.__setattr__(self, "notes", tuple(self.notes))

    @property
    def passed(self) -> bool:
        return self.status is Phase5RegressionStatus.PASSED


def build_phase5_regression_report(
    *,
    suite_id: str = PHASE5_REGRESSION_SUITE_ID,
    baseline_metrics: Mapping[str, float] | None = None,
    evaluation_report: EvaluationReport | None = None,
    incident_report: Mapping[str, object] | None = None,
    lineage_report: Mapping[str, object] | None = None,
    performance_report: Phase5PerformanceReport | None = None,
    post_sft_report: PostSFTEvaluationReport | None = None,
    include_post_sft: bool = True,
    measured_at: datetime | None = None,
) -> Phase5RegressionReport:
    """Run the deterministic Phase 5 suite and compare it to a baseline."""

    if suite_id != PHASE5_REGRESSION_SUITE_ID:
        raise ValueError(f"unsupported suite: {suite_id}")
    timestamp = measured_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("measured_at must include a timezone")

    harness = evaluation_report or build_default_evaluation_report()
    incident = dict(incident_report or run_incident_smoke())
    lineage = dict(lineage_report or run_lineage_smoke())
    performance = performance_report or build_default_performance_report(timestamp)
    sections = [
        _target_resolution_section(harness),
        _search_section(harness),
        _answer_section(harness),
        _risk_section(harness),
        _citation_section(harness),
        _abstention_section(harness),
        _smoke_section(Phase5RegressionSection.INCIDENT, incident, "incident_smoke_passed"),
        _smoke_section(Phase5RegressionSection.LINEAGE, lineage, "lineage_smoke_passed"),
        _performance_section(performance),
    ]
    sections.append(
        _post_sft_section(post_sft_report, include_post_sft=include_post_sft)
    )

    metrics = _flatten_section_metrics(tuple(sections))
    comparisons = compare_metrics_to_baseline(metrics, baseline_metrics or {})
    failed_required_section = any(
        section.required and section.status is Phase5RegressionStatus.FAILED
        for section in sections
    )
    regression_detected = any(comparison.regression_detected for comparison in comparisons)
    status = (
        Phase5RegressionStatus.FAILED
        if failed_required_section or regression_detected
        else Phase5RegressionStatus.PASSED
    )

    return Phase5RegressionReport(
        schema_version=PHASE5_REGRESSION_SCHEMA_VERSION,
        suite_id=suite_id,
        status=status,
        measured_at=timestamp.astimezone(timezone.utc).isoformat(),
        sections=tuple(sections),
        metrics=metrics,
        baseline_comparisons=tuple(comparisons),
        notes=(
            "Default suite uses deterministic cases and checked-in artifacts only.",
            "Heavy model training or live external collection is intentionally out of band.",
        ),
    )


def build_default_evaluation_report() -> EvaluationReport:
    """Return a small deterministic harness report covering all answer buckets."""

    return build_evaluation_report(
        target_cases=(
            TargetResolutionEvaluation("case-target-file", "target-file", "target-file"),
            TargetResolutionEvaluation("case-target-abstain", None, None, should_resolve=False),
        ),
        retrieval_cases=(
            RetrievalEvaluation("case-search", ("source-1", "source-2"), ("source-1", "source-2")),
        ),
        answer_cases=(
            AnswerEvaluation("case-risk", "risk_found", "risk_found", False, False, 0, 0),
            AnswerEvaluation("case-abstain", "no_risk_found", "no_risk_found", True, True, 0, 0),
        ),
    )


def build_default_performance_report(measured_at: datetime) -> Phase5PerformanceReport:
    """Return deterministic performance metrics without local resource probing."""

    return build_phase5_performance_report(
        (
            ChatPerformanceCase(
                case_id="phase5-regression-deterministic-case",
                raw_input=(
                    "https://github.com/example/repo/pull/123 "
                    "src/example.py implementation reason, risk, incident, and lineage"
                ),
            ),
        ),
        resource_sampler=UnknownResourceSampler(),
        clock=_DeterministicClock((0.01, 0.02, 0.03, 0.04, 0.05)),
        measured_at=measured_at,
    )


def compare_metrics_to_baseline(
    metrics: Mapping[str, float],
    baseline_metrics: Mapping[str, float],
    *,
    tolerance: float = 0.0,
) -> tuple[BaselineComparison, ...]:
    """Return metric regressions without mixing stage ownership."""

    comparisons: list[BaselineComparison] = []
    for metric_name, current_value in sorted(metrics.items()):
        if metric_name not in baseline_metrics:
            continue
        baseline_value = float(baseline_metrics[metric_name])
        current = float(current_value)
        direction = _metric_direction(metric_name)
        if direction is MetricDirection.LOWER_IS_BETTER:
            regression = current > baseline_value + tolerance
        else:
            regression = current < baseline_value - tolerance
        comparisons.append(
            BaselineComparison(
                metric_name=metric_name,
                current_value=current,
                baseline_value=baseline_value,
                delta=round(current - baseline_value, 6),
                direction=direction,
                regression_detected=regression,
            )
        )
    return tuple(comparisons)


def load_baseline_metrics(path: str | Path) -> dict[str, float]:
    """Load baseline metrics from a previous report or a plain metrics object."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("baseline must be a JSON object")
    if isinstance(raw.get("metrics"), Mapping):
        return _numeric_mapping(raw["metrics"])  # type: ignore[index]
    if isinstance(raw.get("sections"), list):
        metrics: dict[str, float] = {}
        for section in raw["sections"]:  # type: ignore[index]
            if not isinstance(section, Mapping):
                continue
            section_id = str(section.get("section_id", ""))
            section_metrics = section.get("metrics")
            if not section_id or not isinstance(section_metrics, Mapping):
                continue
            for metric_name, value in section_metrics.items():
                if isinstance(value, int | float):
                    metrics[f"{section_id}.{metric_name}"] = float(value)
        return metrics
    return _numeric_mapping(raw)


def phase5_regression_report_to_dict(report: Phase5RegressionReport) -> dict[str, object]:
    """Return a JSON-friendly suite report."""

    return {
        "schema_version": report.schema_version,
        "suite_id": report.suite_id,
        "status": report.status.value,
        "passed": report.passed,
        "measured_at": report.measured_at,
        "sections": [section.to_dict() for section in report.sections],
        "metrics": dict(report.metrics),
        "baseline_comparisons": [
            comparison.to_dict() for comparison in report.baseline_comparisons
        ],
        "notes": list(report.notes),
    }


def phase5_regression_report_to_json(report: Phase5RegressionReport) -> str:
    """Return formatted JSON for the suite report."""

    return json.dumps(phase5_regression_report_to_dict(report), ensure_ascii=False, indent=2)


def phase5_regression_summary_to_markdown(report: Phase5RegressionReport) -> str:
    """Return a compact human-readable suite summary."""

    lines = [
        "# Phase 5 Regression Suite",
        "",
        f"- Suite: `{report.suite_id}`",
        f"- Status: `{report.status.value}`",
        f"- Measured at: `{report.measured_at}`",
        "",
        "| Section | Status | Required | Metrics |",
        "| --- | --- | --- | --- |",
    ]
    for section in report.sections:
        metric_text = ", ".join(f"{name}={value:.4g}" for name, value in sorted(section.metrics.items()))
        lines.append(
            f"| {section.section_id.value} | {section.status.value} | {section.required} | {metric_text} |"
        )
    if report.baseline_comparisons:
        lines.extend(["", "## Baseline Comparison", ""])
        for comparison in report.baseline_comparisons:
            marker = "REGRESSION" if comparison.regression_detected else "ok"
            lines.append(
                "- "
                f"{comparison.metric_name}: {comparison.current_value:.4g} "
                f"vs {comparison.baseline_value:.4g} "
                f"({comparison.direction.value}, delta {comparison.delta:.4g}) - {marker}"
            )
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines) + "\n"


def write_phase5_regression_report(
    report: Phase5RegressionReport,
    *,
    output_dir: str | Path,
    json_filename: str = "phase5-regression.json",
    markdown_filename: str = "phase5-regression.md",
) -> tuple[Path, Path]:
    """Write suite JSON and Markdown outputs under output_dir."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / json_filename
    markdown_path = root / markdown_filename
    json_path.write_text(phase5_regression_report_to_json(report) + "\n", encoding="utf-8")
    markdown_path.write_text(phase5_regression_summary_to_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def default_phase5_regression_output_dir(
    *,
    data_root: str | Path = "data",
    model_name: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
) -> Path:
    """Return the conventional Phase 5 regression run directory."""

    return Path(data_root) / model_name_to_data_dir_name(model_name) / "runs" / "phase5-regression"


def _target_resolution_section(report: EvaluationReport) -> Phase5RegressionSectionResult:
    failures = _failures_for(report, FailureStage.TARGET_RESOLUTION)
    return _section(
        Phase5RegressionSection.TARGET_RESOLUTION,
        {"accuracy": report.target_resolution_accuracy},
        failures=failures,
    )


def _search_section(report: EvaluationReport) -> Phase5RegressionSectionResult:
    failures = _failures_for(report, FailureStage.SEARCH, FailureStage.RERANK)
    return _section(
        Phase5RegressionSection.SEARCH,
        {
            "evidence_recall_at_k": report.evidence_recall_at_k,
            "mean_reciprocal_rank": report.mean_reciprocal_rank,
        },
        failures=failures,
    )


def _answer_section(report: EvaluationReport) -> Phase5RegressionSectionResult:
    failures = _failures_for(report, FailureStage.GENERATION)
    return _section(
        Phase5RegressionSection.ANSWER,
        {"unsupported_claim_rate": report.unsupported_claim_rate},
        failures=failures,
    )


def _risk_section(report: EvaluationReport) -> Phase5RegressionSectionResult:
    failures = _failures_for(report, FailureStage.RISK)
    return _section(
        Phase5RegressionSection.RISK,
        {
            "risk_label_accuracy": report.risk_label_accuracy,
            "risk_warning_precision": report.risk_warning_precision,
        },
        failures=failures,
    )


def _citation_section(report: EvaluationReport) -> Phase5RegressionSectionResult:
    failures = _failures_for(report, FailureStage.CITATION_VERIFICATION)
    return _section(
        Phase5RegressionSection.CITATION,
        {"citation_consistency_rate": report.citation_consistency_rate},
        failures=failures,
    )


def _abstention_section(report: EvaluationReport) -> Phase5RegressionSectionResult:
    failures = _failures_for(report, FailureStage.ABSTENTION)
    return _section(
        Phase5RegressionSection.ABSTENTION,
        {"abstention_accuracy": report.abstention_accuracy},
        failures=failures,
    )


def _smoke_section(
    section_id: Phase5RegressionSection,
    payload: Mapping[str, object],
    expected_status: str,
) -> Phase5RegressionSectionResult:
    status_value = str(payload.get("status", "missing"))
    passed = status_value == expected_status
    return Phase5RegressionSectionResult(
        section_id=section_id,
        status=Phase5RegressionStatus.PASSED if passed else Phase5RegressionStatus.FAILED,
        required=True,
        metrics={"passed": 1.0 if passed else 0.0},
        failures=() if passed else ({"stage": section_id.value, "reason": status_value},),
        details={"status": status_value},
    )


def _performance_section(report: Phase5PerformanceReport) -> Phase5RegressionSectionResult:
    payload = phase5_performance_report_to_dict(report)
    max_p95 = max(summary.p95_latency_ms for summary in report.stage_summaries)
    return Phase5RegressionSectionResult(
        section_id=Phase5RegressionSection.PERFORMANCE,
        status=Phase5RegressionStatus.PASSED,
        required=True,
        metrics={
            "stage_count": float(len(report.stage_summaries)),
            "max_p95_latency_ms": float(max_p95),
            "bottleneck_p95_latency_ms": float(report.bottleneck.p95_latency_ms),
        },
        details={
            "schema_version": report.schema_version,
            "bottleneck": asdict(report.bottleneck),
            "stage_summaries": payload["stage_summaries"],
        },
    )


def _post_sft_section(
    report: PostSFTEvaluationReport | None,
    *,
    include_post_sft: bool,
) -> Phase5RegressionSectionResult:
    if not include_post_sft:
        return Phase5RegressionSectionResult(
            section_id=Phase5RegressionSection.POST_SFT,
            status=Phase5RegressionStatus.SKIPPED,
            required=False,
            metrics={},
            details={"reason": "post-SFT artifact validation was skipped"},
        )
    try:
        active_report = report or build_post_sft_evaluation_report()
    except Exception as exc:  # pragma: no cover - exercised by CLI in incomplete data roots.
        return Phase5RegressionSectionResult(
            section_id=Phase5RegressionSection.POST_SFT,
            status=Phase5RegressionStatus.FAILED,
            required=True,
            metrics={"passed": 0.0},
            failures=({"stage": "post_sft", "reason": str(exc)},),
        )
    passed = active_report.status == "post_sft_evaluation_passed"
    return Phase5RegressionSectionResult(
        section_id=Phase5RegressionSection.POST_SFT,
        status=Phase5RegressionStatus.PASSED if passed else Phase5RegressionStatus.FAILED,
        required=True,
        metrics={"passed": 1.0 if passed else 0.0},
        failures=() if passed else ({"stage": "post_sft", "reason": active_report.status},),
        details=post_sft_evaluation_report_to_dict(active_report),
    )


def _section(
    section_id: Phase5RegressionSection,
    metrics: dict[str, float],
    *,
    failures: tuple[dict[str, object], ...] = (),
) -> Phase5RegressionSectionResult:
    return Phase5RegressionSectionResult(
        section_id=section_id,
        status=Phase5RegressionStatus.FAILED if failures else Phase5RegressionStatus.PASSED,
        required=True,
        metrics=metrics,
        failures=failures,
    )


def _failures_for(
    report: EvaluationReport,
    *stages: FailureStage,
) -> tuple[dict[str, object], ...]:
    stage_set = set(stages)
    return tuple(
        _failure_to_dict(failure)
        for failure in report.failures
        if failure.stage in stage_set
    )


def _failure_to_dict(failure: FailureClassification) -> dict[str, object]:
    return {
        "case_id": failure.case_id,
        "stage": failure.stage.value,
        "reason": failure.reason,
    }


def _flatten_section_metrics(
    sections: tuple[Phase5RegressionSectionResult, ...],
) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for section in sections:
        for metric_name, value in section.metrics.items():
            metrics[f"{section.section_id.value}.{metric_name}"] = float(value)
    return metrics


def _metric_direction(metric_name: str) -> MetricDirection:
    if metric_name.endswith("_rate") and "unsupported_claim" in metric_name:
        return MetricDirection.LOWER_IS_BETTER
    if metric_name.endswith("_latency_ms") or metric_name.endswith("_p95_latency_ms"):
        return MetricDirection.LOWER_IS_BETTER
    return MetricDirection.HIGHER_IS_BETTER


def _numeric_mapping(raw: Mapping[object, object]) -> dict[str, float]:
    return {
        str(key): float(value)
        for key, value in raw.items()
        if isinstance(value, int | float)
    }


class _DeterministicClock:
    def __init__(self, durations: tuple[float, ...]) -> None:
        self._durations = durations
        self._current = 100.0
        self._call_index = 0

    def __call__(self) -> float:
        stage_index = min(self._call_index // 2, len(self._durations) - 1)
        is_finish_call = self._call_index % 2 == 1
        self._call_index += 1
        if is_finish_call:
            self._current += self._durations[stage_index]
        return self._current


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=PHASE5_REGRESSION_SUITE_ID)
    parser.add_argument("--baseline", type=Path, help="Previous report or metrics JSON for regression detection.")
    parser.add_argument(
        "--output-dir",
        default=str(default_phase5_regression_output_dir()),
        help="Directory for phase5-regression.json and phase5-regression.md.",
    )
    parser.add_argument("--no-write", action="store_true", help="print only; do not write report files")
    parser.add_argument(
        "--skip-post-sft",
        action="store_true",
        help="Skip checked-in post-SFT artifact validation.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    baseline = load_baseline_metrics(args.baseline) if args.baseline else None
    report = build_phase5_regression_report(
        suite_id=args.suite,
        baseline_metrics=baseline,
        include_post_sft=not args.skip_post_sft,
    )
    payload = phase5_regression_report_to_dict(report)
    if not args.no_write:
        json_path, markdown_path = write_phase5_regression_report(
            report,
            output_dir=args.output_dir,
        )
        payload["output_paths"] = [str(json_path), str(markdown_path)]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
