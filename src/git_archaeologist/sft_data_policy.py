"""SFT data policy and schema validation.

The policy keeps fine-tuning focused on answer discipline. Repository facts
must remain in retrieval data and Evidence Packs, not in model parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


SFT_SCHEMA_VERSION = 1
INITIAL_DATA_SOURCE_REPOSITORY = "react/react"
MODEL_DATA_ROOT_PATTERN = "data/<model-name>/"
SFT_DATA_PATH_PATTERN = "data/<model-name>/sft/"
EVAL_DATA_PATH_PATTERN = "data/<model-name>/eval/"

ALLOWED_TRAINING_CONTENT = (
    "reading Evidence Packs and separating supported facts from inference",
    "suppressing assertions when Evidence Packs do not support a claim",
    "citing source IDs that actually support each answer claim",
    "preserving the structured answer format for rationale and risk answers",
    "improving review judgment from evidence-backed constraints and risks",
)

PROHIBITED_TRAINING_CONTENT = (
    "memorizing repository-specific facts, timelines, authors, or decisions",
    "answering from raw GitHub or git artifacts without an Evidence Pack",
    "training on secrets, private data, credentials, or redacted values",
    "teaching unsupported claims, missing citations, or closed-book answers",
    "mixing examples across train, validation, and test decision units",
)

COLLECTION_ERROR_CATEGORIES = (
    "auth_or_permission",
    "rate_limit_or_timeout",
    "partial_or_interrupted_collection",
    "artifact_missing_or_deleted",
    "schema_or_parse_error",
    "redaction_or_secret_detection",
    "storage_integrity_error",
)

HUMAN_ERROR_REPORT_FIELDS = (
    "repository_id",
    "artifact_kind",
    "target",
    "operation",
    "error_type",
    "error_message",
    "source_url",
    "retry_count",
)

HUMAN_ERROR_SUPPRESSED_FIELDS = (
    "raw_token",
    "authorization_header",
    "secret_value",
    "private_key",
)


class Split(str, Enum):
    """Dataset split names used for SFT and evaluation records."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class ExpectedVerdict(str, Enum):
    """Expected evaluator verdict for answer discipline cases."""

    ANSWERABLE = "answerable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SFTRecord:
    """Validated SFT example.

    Required shape: question + target + Evidence Pack + ideal answer.
    """

    schema_version: int
    record_id: str
    source_repository: str
    split: Split
    question: str
    target: Mapping[str, Any]
    evidence_pack: Mapping[str, Any]
    ideal_answer: Mapping[str, Any]
    labels: Mapping[str, Any]


@dataclass(frozen=True)
class EvaluationCase:
    """Validated evaluation case for answer discipline."""

    schema_version: int
    case_id: str
    source_repository: str
    split: Split
    question: str
    target: Mapping[str, Any]
    evidence_pack: Mapping[str, Any]
    expected_behavior: Mapping[str, Any]

    @property
    def is_closed_book_leakage_test(self) -> bool:
        return (
            not _evidence_items(self.evidence_pack)
            and self.expected_behavior.get("verdict") == ExpectedVerdict.UNKNOWN.value
            and self.expected_behavior.get("must_not_answer_closed_book") is True
        )


def validate_sft_record(raw_record: Mapping[str, Any]) -> SFTRecord:
    """Validate and return an SFT record mapping."""

    record = SFTRecord(
        schema_version=_require_schema_version(raw_record),
        record_id=_require_str(raw_record, "record_id"),
        source_repository=_require_str(raw_record, "source_repository"),
        split=Split(_require_str(raw_record, "split")),
        question=_require_str(raw_record, "question"),
        target=_freeze_mapping(_require_mapping(raw_record, "target")),
        evidence_pack=_freeze_mapping(_require_mapping(raw_record, "evidence_pack")),
        ideal_answer=_freeze_mapping(_require_mapping(raw_record, "ideal_answer")),
        labels=_freeze_mapping(_require_mapping(raw_record, "labels")),
    )

    _validate_source_repository(record.source_repository)
    _validate_target(record.target)
    _validate_evidence_pack(record.evidence_pack, require_evidence=True)
    _validate_ideal_answer(record.ideal_answer, record.evidence_pack)
    return record


def validate_evaluation_case(raw_case: Mapping[str, Any]) -> EvaluationCase:
    """Validate and return an evaluation case mapping."""

    case = EvaluationCase(
        schema_version=_require_schema_version(raw_case),
        case_id=_require_str(raw_case, "case_id"),
        source_repository=_require_str(raw_case, "source_repository"),
        split=Split(_require_str(raw_case, "split")),
        question=_require_str(raw_case, "question"),
        target=_freeze_mapping(_require_mapping(raw_case, "target")),
        evidence_pack=_freeze_mapping(_require_mapping(raw_case, "evidence_pack")),
        expected_behavior=_freeze_mapping(
            _require_mapping(raw_case, "expected_behavior")
        ),
    )

    _validate_source_repository(case.source_repository)
    _validate_target(case.target)
    _validate_evidence_pack(case.evidence_pack, require_evidence=False)
    _validate_expected_behavior(case.expected_behavior, case.evidence_pack)
    return case


def _validate_source_repository(source_repository: str) -> None:
    if source_repository != INITIAL_DATA_SOURCE_REPOSITORY:
        raise ValueError(
            "source_repository must use the initial data source: "
            f"{INITIAL_DATA_SOURCE_REPOSITORY}"
        )


def _validate_target(target: Mapping[str, Any]) -> None:
    _require_str(target, "repository_id")
    _require_str(target, "target_type")
    if target["repository_id"] != INITIAL_DATA_SOURCE_REPOSITORY:
        raise ValueError(
            "target.repository_id must match the source repository: "
            f"{INITIAL_DATA_SOURCE_REPOSITORY}"
        )


def _validate_evidence_pack(
    evidence_pack: Mapping[str, Any], *, require_evidence: bool
) -> None:
    _require_str(evidence_pack, "pack_id")
    items = _evidence_items(evidence_pack)
    if require_evidence and not items:
        raise ValueError("evidence_pack.evidence_items must not be empty")
    for item in items:
        _require_str(item, "source_id")
        _require_str(item, "artifact_kind")
        _require_str(item, "source_url")
        _require_str(item, "excerpt")


def _validate_ideal_answer(
    ideal_answer: Mapping[str, Any], evidence_pack: Mapping[str, Any]
) -> None:
    _require_str(ideal_answer, "answer")
    confidence = _require_str(ideal_answer, "confidence")
    if confidence not in {"low", "medium", "high"}:
        raise ValueError("ideal_answer.confidence must be low, medium, or high")

    source_ids = {item["source_id"] for item in _evidence_items(evidence_pack)}
    citations = _require_str_list(ideal_answer, "citations")
    missing_citations = sorted(set(citations) - source_ids)
    if missing_citations:
        raise ValueError(
            "ideal_answer.citations contains unknown source IDs: "
            f"{', '.join(missing_citations)}"
        )

    unsupported_claims = ideal_answer.get("unsupported_claims", [])
    if unsupported_claims:
        raise ValueError("ideal_answer.unsupported_claims must be empty")


def _validate_expected_behavior(
    expected_behavior: Mapping[str, Any], evidence_pack: Mapping[str, Any]
) -> None:
    verdict = ExpectedVerdict(_require_str(expected_behavior, "verdict"))
    must_not_answer_closed_book = _require_bool(
        expected_behavior, "must_not_answer_closed_book"
    )
    if not _evidence_items(evidence_pack) and verdict != ExpectedVerdict.UNKNOWN:
        raise ValueError("empty Evidence Pack evaluation cases must expect unknown")
    if not _evidence_items(evidence_pack) and not must_not_answer_closed_book:
        raise ValueError(
            "closed-book leakage cases must set must_not_answer_closed_book"
        )


def _evidence_items(evidence_pack: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    items = evidence_pack.get("evidence_items", ())
    if not isinstance(items, list | tuple) or not all(
        isinstance(item, Mapping) for item in items
    ):
        raise ValueError("evidence_pack.evidence_items must be a list of objects")
    return tuple(items)


def _require_schema_version(raw: Mapping[str, Any]) -> int:
    schema_version = _require_int(raw, "schema_version")
    if schema_version != SFT_SCHEMA_VERSION:
        raise ValueError(f"unsupported SFT schema_version: {schema_version}")
    return schema_version


def _freeze_mapping(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(raw))


def _require_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = _require(raw, key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _require_str_list(raw: Mapping[str, Any], key: str) -> list[str]:
    value = _require(raw, key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"{key} must be a list of strings")
    return value


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = _require(raw, key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    value = _require(raw, key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _require_bool(raw: Mapping[str, Any], key: str) -> bool:
    value = _require(raw, key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _require(raw: Mapping[str, Any], key: str) -> Any:
    if key not in raw:
        raise ValueError(f"missing required field: {key}")
    return raw[key]
