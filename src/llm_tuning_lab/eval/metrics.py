from __future__ import annotations

from datetime import datetime
from typing import Any

CONFIDENT_TERMS = ("proves", "definitely", "certainly", "明らか", "断定", "証明")


def exact_match(prediction: str, expected: str) -> bool:
    return prediction.strip() == expected.strip()


def evaluate_prediction(prediction: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    predicted_citations = _citation_ids(prediction.get("citations"))
    expected_citations = _citation_ids(expected.get("citations"))
    supported = predicted_citations & expected_citations
    unsupported = predicted_citations - expected_citations
    schema_valid = _schema_valid(prediction)
    timeline_order = _timeline_order_ok(prediction.get("timeline"))

    return {
        "schema_valid": schema_valid,
        "citation_precision": _safe_divide(len(supported), len(predicted_citations)),
        "citation_recall": _safe_divide(len(supported), len(expected_citations)),
        "unsupported_citations": sorted(unsupported),
        "timeline_order": timeline_order,
        "uncertainty_present": bool(str(prediction.get("uncertainty") or "").strip()),
        "insufficient_evidence_caution": _insufficient_evidence_caution(prediction, expected),
    }


def zero_metrics(reason: str) -> dict[str, Any]:
    return {
        "schema_valid": False,
        "citation_precision": 0.0,
        "citation_recall": 0.0,
        "unsupported_citations": [],
        "timeline_order": False,
        "uncertainty_present": False,
        "insufficient_evidence_caution": False,
        "zero_score_reason": reason,
    }


def summarize_metrics(
    results: list[dict[str, Any]],
    *,
    benchmark_count: int | None = None,
    prediction_count: int | None = None,
    duplicate_count: int = 0,
    unknown_count: int = 0,
) -> dict[str, Any]:
    if not results:
        return {
            "count": 0,
            "benchmark_count": benchmark_count or 0,
            "prediction_count": prediction_count or 0,
            "matched_count": 0,
            "missing_count": benchmark_count or 0,
            "duplicate_count": duplicate_count,
            "unknown_count": unknown_count,
            "coverage": 0.0,
        }
    metric_names = (
        "schema_valid",
        "citation_precision",
        "citation_recall",
        "timeline_order",
        "uncertainty_present",
        "insufficient_evidence_caution",
    )
    benchmark_count = benchmark_count if benchmark_count is not None else len(results)
    prediction_count = prediction_count if prediction_count is not None else len(results)
    matched_count = sum(1 for result in results if result.get("status") == "matched")
    missing_count = sum(1 for result in results if result.get("status") == "missing")
    summary: dict[str, Any] = {
        "count": len(results),
        "benchmark_count": benchmark_count,
        "prediction_count": prediction_count,
        "matched_count": matched_count,
        "missing_count": missing_count,
        "duplicate_count": duplicate_count,
        "unknown_count": unknown_count,
        "coverage": _safe_divide(matched_count, benchmark_count),
    }
    for name in metric_names:
        values = [float(result["metrics"][name]) for result in results]
        summary[name] = sum(values) / len(values)
    summary["unsupported_citation_count"] = sum(
        len(result["metrics"]["unsupported_citations"]) for result in results
    )
    return summary


def _schema_valid(prediction: dict[str, Any]) -> bool:
    return (
        isinstance(prediction.get("facts"), list)
        and isinstance(prediction.get("timeline"), list)
        and isinstance(prediction.get("inference"), str)
        and isinstance(prediction.get("uncertainty"), str)
        and isinstance(prediction.get("citations"), list)
        and isinstance(prediction.get("answer"), str)
    )


def _citation_ids(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    citations: set[str] = set()
    for item in value:
        if isinstance(item, str):
            citations.add(item)
        elif isinstance(item, dict) and item.get("evidence_id"):
            citations.add(str(item["evidence_id"]))
    return citations


def _timeline_order_ok(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    previous: datetime | None = None
    for item in value:
        if not isinstance(item, dict):
            return False
        current = _parse_datetime(item.get("date") or item.get("created_at"))
        if current is None:
            continue
        if previous is not None and current < previous:
            return False
        previous = current
    return True


def _insufficient_evidence_caution(prediction: dict[str, Any], expected: dict[str, Any]) -> bool:
    if not expected.get("insufficient_evidence"):
        return True
    text = " ".join(
        str(prediction.get(field) or "") for field in ("answer", "inference", "uncertainty")
    )
    lowered = text.lower()
    if any(term.lower() in lowered for term in CONFIDENT_TERMS):
        return False
    return bool(str(prediction.get("uncertainty") or "").strip())


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_divide(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0 if numerator == 0 else 0.0
    return numerator / denominator
