from __future__ import annotations

import argparse
import json
from pathlib import Path

from llm_tuning_lab.data.bundles import read_jsonl
from llm_tuning_lab.eval.metrics import evaluate_prediction, summarize_metrics, zero_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Score Git Archaeologist evaluation predictions.")
    parser.add_argument("--benchmark", type=Path, default=Path("evals/benchmarks/smoke.jsonl"))
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("evals/results/metrics.json"))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--fail-on-invalid", action="store_true")
    parser.add_argument("--min-coverage", type=float)
    parser.add_argument("--min-answer-similarity", type=float)
    parser.add_argument("--min-fact-recall", type=float)
    parser.add_argument("--min-timeline-event-recall", type=float)
    args = parser.parse_args()

    benchmark_records = list(read_jsonl(args.benchmark))
    benchmark = {str(record["id"]): record for record in benchmark_records}
    if not args.predictions.exists():
        results = [
            {
                "id": str(record["id"]),
                "status": "missing",
                "metrics": zero_metrics("prediction file missing"),
            }
            for record in benchmark_records
        ]
        _write_json(
            args.output,
            {
                "status": "missing_predictions",
                "summary": summarize_metrics(
                    results,
                    benchmark_count=len(benchmark_records),
                    prediction_count=0,
                ),
                "results": results,
            },
        )
        print(f"missing predictions: {args.predictions}")
        return 2 if args.strict else 0

    predictions = list(read_jsonl(args.predictions))
    prediction_by_id: dict[str, dict] = {}
    duplicate_ids: set[str] = set()
    duplicate_count = 0
    for prediction_record in predictions:
        record_id = str(prediction_record.get("id"))
        if record_id in prediction_by_id:
            duplicate_ids.add(record_id)
            duplicate_count += 1
            continue
        prediction_by_id[record_id] = prediction_record

    unknown_ids = sorted(set(prediction_by_id) - set(benchmark))
    results = []
    for expected_record in benchmark_records:
        record_id = str(expected_record["id"])
        prediction_record = prediction_by_id.get(record_id)
        if prediction_record is None:
            results.append(
                {
                    "id": record_id,
                    "status": "missing",
                    "metrics": zero_metrics("prediction missing"),
                }
            )
            continue
        prediction = prediction_record.get("prediction")
        if not isinstance(prediction, dict):
            prediction = {}
        results.append(
            {
                "id": record_id,
                "status": "matched",
                "metrics": evaluate_prediction(prediction, expected_record["expected"]),
            }
        )

    for unknown_id in unknown_ids:
        results.append(
            {
                "id": unknown_id,
                "status": "unknown",
                "metrics": zero_metrics("prediction id not found in benchmark"),
            }
        )

    status = "ok" if not duplicate_ids and not unknown_ids else "invalid_predictions"
    summary = summarize_metrics(
        results,
        benchmark_count=len(benchmark_records),
        prediction_count=len(predictions),
        duplicate_count=duplicate_count,
        unknown_count=len(unknown_ids),
    )
    threshold_failures = _threshold_failures(args, summary)
    if threshold_failures:
        status = "threshold_failed"
    _write_json(
        args.output,
        {
            "status": status,
            "summary": summary,
            "threshold_failures": threshold_failures,
            "duplicate_ids": sorted(duplicate_ids),
            "unknown_ids": unknown_ids,
            "results": results,
        },
    )
    print(f"metrics: {args.output}")
    if (args.strict or args.fail_on_invalid) and (duplicate_ids or unknown_ids):
        return 1
    if threshold_failures:
        if any(failure["metric"] == "coverage" for failure in threshold_failures):
            return 3
        return 4
    return 0


def _threshold_failures(args: argparse.Namespace, summary: dict) -> list[dict]:
    checks = {
        "coverage": args.min_coverage,
        "answer_similarity": args.min_answer_similarity,
        "fact_recall": args.min_fact_recall,
        "timeline_event_recall": args.min_timeline_event_recall,
    }
    failures = []
    for metric, minimum in checks.items():
        if minimum is None:
            continue
        actual = float(summary.get(metric, 0.0))
        if actual < minimum:
            failures.append({"metric": metric, "minimum": minimum, "actual": actual})
    return failures


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
