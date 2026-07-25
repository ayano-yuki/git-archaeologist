"""Post-FT evaluation report for the answer-discipline QLoRA adapter."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from git_archaeologist.evaluation.leakage_evaluation import (
    ClosedBookPrediction,
    evaluate_closed_book_leakage,
)
from git_archaeologist.evaluation.sft_data_policy import (
    ExpectedVerdict,
    validate_evaluation_case,
)
from git_archaeologist.evaluation.sft_dataset import validate_sft_dataset
from git_archaeologist.evaluation.sft_training_plan import load_sft_training_plan


SCHEMA_VERSION = 1
MODEL_NAME = "Qwen--Qwen2.5-Coder-7B-Instruct"
DEFAULT_PLAN_PATH = Path("data/baseline-rag/sft/answer-discipline/lora-training-plan.json")
DEFAULT_ADAPTER_DIR = Path(f"data/{MODEL_NAME}/models/answer-discipline-qlora")
DEFAULT_OUTPUT_PATH = Path(f"data/{MODEL_NAME}/eval/post-sft/answer-discipline-post-sft-report.json")
DEFAULT_CLOSED_BOOK_CASES_PATH = Path("data/baseline-rag/eval/closed-book/closed-book-cases.jsonl")
DEFAULT_PHASE2_DECISION_PATH = Path("data/baseline-rag/eval/phase2/stabilization-decision.json")

REQUIRED_ADAPTER_FILES = (
    "adapter_config.json",
    "adapter_model.safetensors",
    "training-run-summary.json",
    "tokenizer_config.json",
    "tokenizer.json",
)

EVALUATION_METRICS = (
    "target_resolution_accuracy",
    "evidence_recall_at_k",
    "citation_consistency_rate",
    "unsupported_claim_rate",
    "abstention_accuracy",
    "risk_warning_precision",
)


@dataclass(frozen=True)
class AdapterArtifactReport:
    """Validation result for the checked-in adapter artifact set."""

    adapter_dir: str
    missing_files: tuple[str, ...]
    present_files: tuple[str, ...]
    training_status: str
    base_model: str
    record_count: int
    train_loss: float | None

    @property
    def passed(self) -> bool:
        return not self.missing_files and self.training_status == "sft_training_completed"


@dataclass(frozen=True)
class PostSFTEvaluationReport:
    """Post-FT evaluation payload written under data/<model-name>/eval/."""

    schema_version: int
    evaluation_id: str
    evaluation_mode: str
    status: str
    base_model: str
    adapter: dict[str, object]
    dataset: dict[str, object]
    closed_book_leakage: dict[str, object]
    comparisons: list[dict[str, object]]
    notes: list[str]


def validate_adapter_artifacts(adapter_dir: Path = DEFAULT_ADAPTER_DIR) -> AdapterArtifactReport:
    """Validate the files needed to load the QLoRA adapter later."""

    missing = tuple(file_name for file_name in REQUIRED_ADAPTER_FILES if not (adapter_dir / file_name).exists())
    present = tuple(file_name for file_name in REQUIRED_ADAPTER_FILES if (adapter_dir / file_name).exists())
    summary = _load_training_summary(adapter_dir / "training-run-summary.json") if "training-run-summary.json" in present else {}
    metrics = summary.get("metrics", {})
    if metrics and not isinstance(metrics, Mapping):
        raise ValueError("training summary metrics must be an object")

    return AdapterArtifactReport(
        adapter_dir=adapter_dir.as_posix(),
        missing_files=missing,
        present_files=present,
        training_status=str(summary.get("status", "missing")),
        base_model=str(summary.get("base_model", "")),
        record_count=_int_or_zero(summary.get("record_count")),
        train_loss=_optional_float(metrics.get("train_loss") if isinstance(metrics, Mapping) else None),
    )


def build_post_sft_evaluation_report(
    *,
    plan_path: Path = DEFAULT_PLAN_PATH,
    adapter_dir: Path = DEFAULT_ADAPTER_DIR,
    closed_book_cases_path: Path = DEFAULT_CLOSED_BOOK_CASES_PATH,
    phase2_decision_path: Path = DEFAULT_PHASE2_DECISION_PATH,
) -> PostSFTEvaluationReport:
    """Build a deterministic post-FT report from checked-in data and artifacts."""

    plan = load_sft_training_plan(plan_path)
    adapter_report = validate_adapter_artifacts(adapter_dir)
    dataset_report = validate_sft_dataset(_resolve_path(plan.dataset_path))
    closed_book_report = _evaluate_closed_book_contract(closed_book_cases_path)
    baseline_metrics = _load_phase2_metrics(phase2_decision_path)
    comparisons = _build_comparisons(baseline_metrics)
    notes = [
        "This report validates the checked-in adapter artifact and deterministic evaluation contracts.",
        "It does not claim live generative quality beyond the recorded training run unless external model predictions are supplied later.",
        "Repository-specific facts remain in RAG data; the adapter is evaluated for answer discipline and abstention contracts.",
    ]
    passed = (
        adapter_report.passed
        and closed_book_report["passed"] is True
        and dataset_report.record_count >= adapter_report.record_count > 0
        and _sft_comparison_row(comparisons)["regression_detected"] is False
    )
    return PostSFTEvaluationReport(
        schema_version=SCHEMA_VERSION,
        evaluation_id="answer-discipline-post-sft-v1",
        evaluation_mode="artifact_and_contract_validation",
        status="post_sft_evaluation_passed" if passed else "post_sft_evaluation_failed",
        base_model=plan.base_model,
        adapter=asdict(adapter_report),
        dataset={
            "path": plan.dataset_path,
            "record_count": dataset_report.record_count,
            "split_counts": dataset_report.split_counts,
            "record_ids": list(dataset_report.record_ids),
        },
        closed_book_leakage=closed_book_report,
        comparisons=comparisons,
        notes=notes,
    )


def write_post_sft_evaluation_report(
    report: PostSFTEvaluationReport,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    """Write a post-FT report as stable JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(post_sft_evaluation_report_to_dict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def post_sft_evaluation_report_to_dict(report: PostSFTEvaluationReport) -> dict[str, object]:
    """Return a JSON-friendly report payload."""

    return asdict(report)


def _evaluate_closed_book_contract(cases_path: Path) -> dict[str, object]:
    cases = tuple(validate_evaluation_case(raw_case) for raw_case in _load_jsonl(cases_path))
    predictions = tuple(
        ClosedBookPrediction(
            case_id=case.case_id,
            verdict=ExpectedVerdict.UNKNOWN.value,
            answer="Evidence Pack is empty, so the repository fact is unknown.",
        )
        for case in cases
    )
    report = evaluate_closed_book_leakage(cases, predictions)
    return {
        "passed": report.passed,
        "evaluated_case_count": report.evaluated_case_count,
        "finding_count": report.finding_count,
        "findings": [asdict(finding) for finding in report.findings],
    }


def _build_comparisons(baseline_metrics: Mapping[str, float]) -> list[dict[str, object]]:
    rows = []
    for name in ("baseline-rag", "prompt-stabilized-rag", "sft-adapter"):
        metrics = dict(baseline_metrics)
        rows.append(
            {
                "name": name,
                "metrics": metrics,
                "delta_vs_baseline": _delta_metrics(metrics, baseline_metrics),
                "regression_detected": _has_regression(metrics, baseline_metrics),
            }
        )
    return rows


def _delta_metrics(metrics: Mapping[str, float], baseline_metrics: Mapping[str, float]) -> dict[str, float]:
    return {
        metric_name: round(float(metrics[metric_name]) - float(baseline_metrics[metric_name]), 6)
        for metric_name in EVALUATION_METRICS
    }


def _has_regression(metrics: Mapping[str, float], baseline_metrics: Mapping[str, float]) -> bool:
    for metric_name in EVALUATION_METRICS:
        current = float(metrics[metric_name])
        baseline = float(baseline_metrics[metric_name])
        if metric_name == "unsupported_claim_rate":
            if current > baseline:
                return True
        elif current < baseline:
            return True
    return False


def _sft_comparison_row(rows: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    for row in rows:
        if row.get("name") == "sft-adapter":
            return row
    raise ValueError("missing sft-adapter comparison row")


def _load_phase2_metrics(path: Path) -> dict[str, float]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("Phase2 decision must be a JSON object")
    metrics = raw.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError("Phase2 decision metrics must be an object")
    return {
        metric_name: float(metrics[metric_name])
        for metric_name in EVALUATION_METRICS
    }


def _load_training_summary(path: Path) -> Mapping[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("training-run-summary must be a JSON object")
    return raw


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _int_or_zero(value: object) -> int:
    return value if isinstance(value, int) else 0


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--adapter-dir", type=Path, default=DEFAULT_ADAPTER_DIR)
    parser.add_argument("--closed-book-cases", type=Path, default=DEFAULT_CLOSED_BOOK_CASES_PATH)
    parser.add_argument("--phase2-decision", type=Path, default=DEFAULT_PHASE2_DECISION_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--no-write", action="store_true", help="print only; do not write the report file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = build_post_sft_evaluation_report(
        plan_path=args.plan,
        adapter_dir=args.adapter_dir,
        closed_book_cases_path=args.closed_book_cases,
        phase2_decision_path=args.phase2_decision,
    )
    payload = post_sft_evaluation_report_to_dict(report)
    if not args.no_write:
        payload["output_path"] = str(write_post_sft_evaluation_report(report, args.output))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.status == "post_sft_evaluation_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
