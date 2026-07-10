from __future__ import annotations

from datetime import datetime
import re
from typing import Any

CONFIDENT_TERMS = ("proves", "definitely", "certainly", "明らか", "断定", "証明")
OUTPUT_SCHEMA_VERSION = "git-archaeologist.answer.v1"
ALLOWED_OUTPUT_FIELDS = {
    "schema_version",
    "facts",
    "timeline",
    "inference",
    "uncertainty",
    "citations",
    "answer",
}
TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u3040-\u30ff\u3400-\u9fff]", re.IGNORECASE)


def exact_match(prediction: str, expected: str) -> bool:
    return prediction.strip() == expected.strip()


def evaluate_prediction(prediction: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    predicted_citations = _citation_ids(prediction.get("citations"))
    expected_citations = _citation_ids(expected.get("citations"))
    supported = predicted_citations & expected_citations
    unsupported = predicted_citations - expected_citations
    schema_valid = _schema_valid(prediction)
    timeline_order = _timeline_order_ok(prediction.get("timeline"))
    fact_metrics = _evaluate_fact_items(prediction.get("facts"), expected.get("facts"))
    timeline_metrics = _evaluate_timeline_items(
        prediction.get("timeline"),
        expected.get("timeline"),
    )
    answer_similarity = _text_similarity(prediction.get("answer"), expected.get("answer"))
    inference_similarity = _text_similarity(
        prediction.get("inference"),
        expected.get("inference"),
    )

    return {
        "schema_valid": schema_valid,
        "citation_precision": _safe_divide(len(supported), len(predicted_citations)),
        "citation_recall": _safe_divide(len(supported), len(expected_citations)),
        "unsupported_citations": sorted(unsupported),
        "timeline_order": timeline_order,
        "uncertainty_present": bool(str(prediction.get("uncertainty") or "").strip()),
        "insufficient_evidence_caution": _insufficient_evidence_caution(prediction, expected),
        "fact_precision": fact_metrics["precision"],
        "fact_recall": fact_metrics["recall"],
        "fact_citation_precision": fact_metrics["citation_precision"],
        "fact_citation_recall": fact_metrics["citation_recall"],
        "timeline_event_precision": timeline_metrics["precision"],
        "timeline_event_recall": timeline_metrics["recall"],
        "timeline_date_precision": timeline_metrics["date_precision"],
        "timeline_date_recall": timeline_metrics["date_recall"],
        "answer_similarity": answer_similarity,
        "inference_similarity": inference_similarity,
        "unsupported_claim_count": (
            fact_metrics["unmatched_prediction_count"]
            + timeline_metrics["unmatched_prediction_count"]
            + (1 if answer_similarity < 0.35 else 0)
            + (1 if inference_similarity < 0.35 else 0)
        ),
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
        "fact_precision": 0.0,
        "fact_recall": 0.0,
        "fact_citation_precision": 0.0,
        "fact_citation_recall": 0.0,
        "timeline_event_precision": 0.0,
        "timeline_event_recall": 0.0,
        "timeline_date_precision": 0.0,
        "timeline_date_recall": 0.0,
        "answer_similarity": 0.0,
        "inference_similarity": 0.0,
        "unsupported_claim_count": 0,
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
        "fact_precision",
        "fact_recall",
        "fact_citation_precision",
        "fact_citation_recall",
        "timeline_event_precision",
        "timeline_event_recall",
        "timeline_date_precision",
        "timeline_date_recall",
        "answer_similarity",
        "inference_similarity",
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
    summary["unsupported_claim_count"] = sum(
        int(result["metrics"]["unsupported_claim_count"]) for result in results
    )
    return summary


def _schema_valid(prediction: dict[str, Any]) -> bool:
    if set(prediction) - ALLOWED_OUTPUT_FIELDS:
        return False
    if prediction.get("schema_version") != OUTPUT_SCHEMA_VERSION:
        return False
    if not _valid_fact_items(prediction.get("facts")):
        return False
    if not _valid_timeline_items(prediction.get("timeline")):
        return False
    return all(
        isinstance(prediction.get(field), str) and bool(prediction[field].strip())
        for field in ("inference", "uncertainty", "answer")
    ) and _valid_citation_list(prediction.get("citations"))


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
            return False
        if previous is not None and current < previous:
            return False
        previous = current
    return True


def _evaluate_fact_items(predicted: Any, expected: Any) -> dict[str, float | int]:
    predicted_items = _clean_fact_items(predicted)
    expected_items = _clean_fact_items(expected)
    matches = _match_items(
        predicted_items,
        expected_items,
        text_weight=0.75,
        citation_weight=0.25,
        date_weight=0.0,
        min_text_similarity=0.45,
        min_score=0.55,
    )
    citation_precision_values = []
    citation_recall_values = []
    for predicted_index, expected_index, _ in matches:
        predicted_citations = _citation_ids(predicted_items[predicted_index].get("citations"))
        expected_citations = _citation_ids(expected_items[expected_index].get("citations"))
        overlap = predicted_citations & expected_citations
        citation_precision_values.append(_safe_divide(len(overlap), len(predicted_citations)))
        citation_recall_values.append(_safe_divide(len(overlap), len(expected_citations)))
    return {
        "precision": _safe_divide(len(matches), len(predicted_items)),
        "recall": _safe_divide(len(matches), len(expected_items)),
        "citation_precision": _mean(citation_precision_values),
        "citation_recall": _mean(citation_recall_values),
        "unmatched_prediction_count": len(predicted_items) - len(matches),
    }


def _evaluate_timeline_items(predicted: Any, expected: Any) -> dict[str, float | int]:
    predicted_items = _clean_timeline_items(predicted)
    expected_items = _clean_timeline_items(expected)
    matches = _match_items(
        predicted_items,
        expected_items,
        text_weight=0.55,
        citation_weight=0.2,
        date_weight=0.25,
        min_text_similarity=0.35,
        min_score=0.55,
    )
    date_matches = [
        1.0
        for predicted_index, expected_index, _ in matches
        if _date_key(predicted_items[predicted_index]) == _date_key(expected_items[expected_index])
    ]
    return {
        "precision": _safe_divide(len(matches), len(predicted_items)),
        "recall": _safe_divide(len(matches), len(expected_items)),
        "date_precision": _safe_divide(len(date_matches), len(predicted_items)),
        "date_recall": _safe_divide(len(date_matches), len(expected_items)),
        "unmatched_prediction_count": len(predicted_items) - len(matches),
    }


def _match_items(
    predicted_items: list[dict[str, Any]],
    expected_items: list[dict[str, Any]],
    *,
    text_weight: float,
    citation_weight: float,
    date_weight: float,
    min_text_similarity: float,
    min_score: float,
) -> list[tuple[int, int, float]]:
    candidates: list[tuple[float, int, int]] = []
    for predicted_index, predicted_item in enumerate(predicted_items):
        for expected_index, expected_item in enumerate(expected_items):
            text_score = _text_similarity(predicted_item.get("text"), expected_item.get("text"))
            citation_score = _citation_similarity(
                predicted_item.get("citations"),
                expected_item.get("citations"),
            )
            date_score = 1.0 if _date_key(predicted_item) == _date_key(expected_item) else 0.0
            score = (
                text_weight * text_score
                + citation_weight * citation_score
                + date_weight * date_score
            )
            if text_score >= min_text_similarity and score >= min_score:
                candidates.append((score, predicted_index, expected_index))
    candidates.sort(reverse=True)
    used_predictions: set[int] = set()
    used_expected: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for score, predicted_index, expected_index in candidates:
        if predicted_index in used_predictions or expected_index in used_expected:
            continue
        used_predictions.add(predicted_index)
        used_expected.add(expected_index)
        matches.append((predicted_index, expected_index, score))
    return matches


def _valid_fact_items(value: Any) -> bool:
    return bool(_clean_fact_items(value))


def _valid_timeline_items(value: Any) -> bool:
    return bool(_clean_timeline_items(value))


def _clean_fact_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        citations = item.get("citations")
        if isinstance(text, str) and text.strip() and _valid_citation_list(citations):
            items.append({"text": text, "citations": citations})
    return items


def _clean_timeline_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        citations = item.get("citations")
        when = _parse_datetime(item.get("date") or item.get("created_at"))
        if isinstance(text, str) and text.strip() and _valid_citation_list(citations) and when:
            items.append(
                {
                    "text": text,
                    "citations": citations,
                    "date": item.get("date") or item.get("created_at"),
                }
            )
    return items


def _date_key(item: dict[str, Any]) -> str:
    when = _parse_datetime(item.get("date") or item.get("created_at"))
    return when.date().isoformat() if when else ""


def _valid_citation_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _citation_similarity(predicted: Any, expected: Any) -> float:
    predicted_citations = _citation_ids(predicted)
    expected_citations = _citation_ids(expected)
    overlap = predicted_citations & expected_citations
    precision = _safe_divide(len(overlap), len(predicted_citations))
    recall = _safe_divide(len(overlap), len(expected_citations))
    return _f1(precision, recall)


def _text_similarity(predicted: Any, expected: Any) -> float:
    predicted_tokens = set(_tokens(predicted))
    expected_tokens = set(_tokens(expected))
    if not predicted_tokens and not expected_tokens:
        return 1.0
    if not predicted_tokens or not expected_tokens:
        return 0.0
    overlap = predicted_tokens & expected_tokens
    precision = len(overlap) / len(predicted_tokens)
    recall = len(overlap) / len(expected_tokens)
    return _f1(precision, recall)


def _tokens(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(value)]


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


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
