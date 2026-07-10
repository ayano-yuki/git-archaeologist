import json
import sys
from pathlib import Path

from llm_tuning_lab.eval.run_eval import main


def test_run_eval_scores_missing_predictions_against_benchmark(tmp_path: Path, monkeypatch) -> None:
    benchmark = tmp_path / "benchmark.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    output = tmp_path / "metrics.json"
    benchmark.write_text(
        json.dumps({"id": "case-1", "expected": _expected()}, ensure_ascii=False) + "\n"
        + json.dumps({"id": "case-2", "expected": _expected()}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    predictions.write_text(
        json.dumps({"id": "case-1", "prediction": _prediction()}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_eval",
            "--benchmark",
            str(benchmark),
            "--predictions",
            str(predictions),
            "--output",
            str(output),
        ],
    )

    assert main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))

    assert result["summary"]["benchmark_count"] == 2
    assert result["summary"]["prediction_count"] == 1
    assert result["summary"]["matched_count"] == 1
    assert result["summary"]["missing_count"] == 1
    assert result["summary"]["coverage"] == 0.5


def test_run_eval_strict_fails_when_predictions_are_missing(tmp_path: Path, monkeypatch) -> None:
    benchmark = tmp_path / "benchmark.jsonl"
    predictions = tmp_path / "missing.jsonl"
    output = tmp_path / "metrics.json"
    benchmark.write_text(
        json.dumps({"id": "case-1", "expected": _expected()}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_eval",
            "--benchmark",
            str(benchmark),
            "--predictions",
            str(predictions),
            "--output",
            str(output),
            "--strict",
        ],
    )

    assert main() == 2


def test_run_eval_reports_duplicate_and_unknown_ids(tmp_path: Path, monkeypatch) -> None:
    benchmark = tmp_path / "benchmark.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    output = tmp_path / "metrics.json"
    benchmark.write_text(
        json.dumps({"id": "case-1", "expected": _expected()}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    predictions.write_text(
        json.dumps({"id": "case-1", "prediction": _prediction()}, ensure_ascii=False) + "\n"
        + json.dumps({"id": "case-1", "prediction": _prediction()}, ensure_ascii=False) + "\n"
        + json.dumps({"id": "unknown", "prediction": _prediction()}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_eval",
            "--benchmark",
            str(benchmark),
            "--predictions",
            str(predictions),
            "--output",
            str(output),
        ],
    )

    assert main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))

    assert result["status"] == "invalid_predictions"
    assert result["summary"]["duplicate_count"] == 1
    assert result["summary"]["unknown_count"] == 1
    assert result["duplicate_ids"] == ["case-1"]
    assert result["unknown_ids"] == ["unknown"]


def test_run_eval_threshold_failure_returns_nonzero(tmp_path: Path, monkeypatch) -> None:
    benchmark = tmp_path / "benchmark.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    output = tmp_path / "metrics.json"
    benchmark.write_text(
        json.dumps({"id": "case-1", "expected": _expected()}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    prediction = _prediction()
    prediction["answer"] = "Preference."
    predictions.write_text(
        json.dumps({"id": "case-1", "prediction": prediction}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_eval",
            "--benchmark",
            str(benchmark),
            "--predictions",
            str(predictions),
            "--output",
            str(output),
            "--min-answer-similarity",
            "0.9",
        ],
    )

    assert main() == 4
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "threshold_failed"
    assert result["threshold_failures"][0]["metric"] == "answer_similarity"


def _expected() -> dict:
    return {
        "facts": [{"text": "Fact", "citations": ["e1"]}],
        "citations": ["e1"],
        "timeline": [{"date": "2026-01-01T00:00:00Z", "text": "Event", "citations": ["e1"]}],
        "inference": "Likely reason.",
        "uncertainty": "Some uncertainty.",
        "answer": "Answer.",
    }


def _prediction() -> dict:
    return {
        "schema_version": "git-archaeologist.answer.v1",
        "facts": [{"text": "Fact", "citations": ["e1"]}],
        "citations": ["e1"],
        "timeline": [{"date": "2026-01-01T00:00:00Z", "text": "Event", "citations": ["e1"]}],
        "inference": "Likely reason.",
        "uncertainty": "Some uncertainty.",
        "answer": "Answer.",
    }
