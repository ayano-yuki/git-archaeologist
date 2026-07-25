"""Validated answer schema for RAG-backed responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping


ANSWER_SCHEMA_VERSION = 1


class AnswerVerdict(StrEnum):
    """Top-level answer judgement."""

    EXPLAINED = "explained"
    RISK_FOUND = "risk_found"
    NO_RISK_FOUND = "no_risk_found"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Confidence(StrEnum):
    """Human-readable confidence bands."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Citation:
    """Citation to one Evidence Pack item."""

    source_id: str
    source_url: str
    supports: str

    def validate(self) -> None:
        _require_non_empty(self.source_id, "citation.source_id")
        _require_http_url(self.source_url, "citation.source_url")
        _require_non_empty(self.supports, "citation.supports")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class AnswerClaim:
    """Claim separated by provenance class."""

    text: str
    citation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "citation_ids", tuple(self.citation_ids))

    def validate(self, *, citation_required: bool) -> None:
        _require_non_empty(self.text, "claim.text")
        if citation_required and not self.citation_ids:
            raise AnswerSchemaViolation("fact claims must cite at least one evidence item")
        if any(not citation_id for citation_id in self.citation_ids):
            raise AnswerSchemaViolation("citation IDs must be non-empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "citation_ids": list(self.citation_ids),
        }


@dataclass(frozen=True)
class StructuredAnswer:
    """Stable answer shape shared by generation, evaluation, and UI."""

    verdict: AnswerVerdict
    confirmed_reasons: tuple[AnswerClaim, ...]
    evidence: tuple[Citation, ...]
    inferences: tuple[AnswerClaim, ...] = ()
    potential_risks: tuple[AnswerClaim, ...] = ()
    recommended_actions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    confidence: Confidence = Confidence.MEDIUM
    schema_version: int = ANSWER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "confirmed_reasons", tuple(self.confirmed_reasons))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "inferences", tuple(self.inferences))
        object.__setattr__(self, "potential_risks", tuple(self.potential_risks))
        object.__setattr__(self, "recommended_actions", tuple(self.recommended_actions))
        object.__setattr__(self, "missing_information", tuple(self.missing_information))
        self.validate()

    def validate(self) -> None:
        if self.schema_version != ANSWER_SCHEMA_VERSION:
            raise AnswerSchemaViolation("unsupported answer schema_version")
        citation_ids = set()
        for citation in self.evidence:
            citation.validate()
            citation_ids.add(citation.source_id)
        for claim in self.confirmed_reasons:
            claim.validate(citation_required=True)
            _validate_claim_citations(claim, citation_ids)
        for claim in (*self.inferences, *self.potential_risks):
            claim.validate(citation_required=False)
            _validate_claim_citations(claim, citation_ids)
        for item in (*self.recommended_actions, *self.missing_information):
            _require_non_empty(item, "answer list item")
        if self.verdict == AnswerVerdict.INSUFFICIENT_EVIDENCE and not self.missing_information:
            raise AnswerSchemaViolation(
                "insufficient_evidence answers must list missing_information"
            )

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "verdict": self.verdict.value,
            "confirmed_reasons": [claim.to_dict() for claim in self.confirmed_reasons],
            "evidence": [citation.to_dict() for citation in self.evidence],
            "inferences": [claim.to_dict() for claim in self.inferences],
            "potential_risks": [claim.to_dict() for claim in self.potential_risks],
            "recommended_actions": list(self.recommended_actions),
            "missing_information": list(self.missing_information),
            "confidence": self.confidence.value,
        }


class AnswerSchemaViolation(ValueError):
    """Raised when an answer cannot be safely evaluated or displayed."""


def validate_answer(raw_answer: Mapping[str, Any]) -> StructuredAnswer:
    """Validate a plain mapping and return a typed StructuredAnswer."""

    return StructuredAnswer(
        schema_version=_require_int(raw_answer, "schema_version"),
        verdict=AnswerVerdict(_require_str(raw_answer, "verdict")),
        confirmed_reasons=tuple(
            _claim_from_mapping(item)
            for item in _require_mapping_sequence(raw_answer, "confirmed_reasons")
        ),
        evidence=tuple(
            _citation_from_mapping(item)
            for item in _require_mapping_sequence(raw_answer, "evidence")
        ),
        inferences=tuple(
            _claim_from_mapping(item)
            for item in _mapping_sequence(raw_answer.get("inferences", ()), "inferences")
        ),
        potential_risks=tuple(
            _claim_from_mapping(item)
            for item in _mapping_sequence(
                raw_answer.get("potential_risks", ()), "potential_risks"
            )
        ),
        recommended_actions=tuple(
            _str_sequence(raw_answer.get("recommended_actions", ()), "recommended_actions")
        ),
        missing_information=tuple(
            _str_sequence(raw_answer.get("missing_information", ()), "missing_information")
        ),
        confidence=Confidence(_require_str(raw_answer, "confidence")),
    )


def safe_schema_error(error: Exception) -> dict[str, object]:
    """Return the safe error shape used when answer validation fails."""

    return {
        "schema_version": ANSWER_SCHEMA_VERSION,
        "verdict": AnswerVerdict.INSUFFICIENT_EVIDENCE.value,
        "confirmed_reasons": [],
        "evidence": [],
        "inferences": [],
        "potential_risks": [],
        "recommended_actions": ["Regenerate the answer with a valid structured schema."],
        "missing_information": [str(error)],
        "confidence": Confidence.LOW.value,
    }


def _claim_from_mapping(raw: Mapping[str, Any]) -> AnswerClaim:
    return AnswerClaim(
        text=_require_str(raw, "text"),
        citation_ids=tuple(_str_sequence(raw.get("citation_ids", ()), "citation_ids")),
    )


def _citation_from_mapping(raw: Mapping[str, Any]) -> Citation:
    return Citation(
        source_id=_require_str(raw, "source_id"),
        source_url=_require_str(raw, "source_url"),
        supports=_require_str(raw, "supports"),
    )


def _validate_claim_citations(claim: AnswerClaim, citation_ids: set[str]) -> None:
    missing = set(claim.citation_ids) - citation_ids
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise AnswerSchemaViolation(f"claim references unknown citation IDs: {missing_text}")


def _require_mapping_sequence(raw: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    return _mapping_sequence(_require(raw, key), key)


def _mapping_sequence(value: Any, key: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list | tuple) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise AnswerSchemaViolation(f"{key} must be a list of objects")
    return tuple(value)


def _str_sequence(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not all(isinstance(item, str) and item for item in value):
        raise AnswerSchemaViolation(f"{key} must be a list of non-empty strings")
    return tuple(value)


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = _require(raw, key)
    if not isinstance(value, str) or not value:
        raise AnswerSchemaViolation(f"{key} must be a non-empty string")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    value = _require(raw, key)
    if not isinstance(value, int):
        raise AnswerSchemaViolation(f"{key} must be an integer")
    return value


def _require(raw: Mapping[str, Any], key: str) -> Any:
    if key not in raw:
        raise AnswerSchemaViolation(f"missing required field: {key}")
    return raw[key]


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise AnswerSchemaViolation(f"{field_name} must be a non-empty string")


def _require_http_url(value: str, field_name: str) -> None:
    if not value.startswith(("https://", "http://")):
        raise AnswerSchemaViolation(f"{field_name} must be an http or https URL")
