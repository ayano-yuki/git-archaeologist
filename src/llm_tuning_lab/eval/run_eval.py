from __future__ import annotations

import argparse
import json
from pathlib import Path

from llm_tuning_lab.data.bundles import read_jsonl
from llm_tuning_lab.eval.metrics import evaluate_prediction, summarize_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Score Git Archaeologist evaluation predictions.")
    parser.add_argument("--benchmark", type=Path, default=Path("evals/benchmarks/smoke.jsonl"))
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("evals/results/metrics.json"))
    args = parser.parse_args()

    if not args.predictions.exists():
        _write_json(args.output, {"status": "missing_predictions", "count": 0})
        print(f"missing predictions: {args.predictions}")
        return 0

    benchmark = {str(record["id"]): record for record in read_jsonl(args.benchmark)}
    predictions = list(read_jsonl(args.predictions))
    results = []
    for prediction_record in predictions:
        record_id = str(prediction_record.get("id"))
        expected_record = benchmark.get(record_id)
        if expected_record is None:
            results.append(
                {
                    "id": record_id,
                    "error": "prediction id not found in benchmark",
                    "metrics": evaluate_prediction({}, {}),
                }
            )
            continue
        prediction = prediction_record.get("prediction")
        if not isinstance(prediction, dict):
            prediction = {}
        results.append(
            {
                "id": record_id,
                "metrics": evaluate_prediction(prediction, expected_record["expected"]),
            }
        )

    _write_json(args.output, {"status": "ok", "summary": summarize_metrics(results), "results": results})
    print(f"metrics: {args.output}")
    return 0


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
