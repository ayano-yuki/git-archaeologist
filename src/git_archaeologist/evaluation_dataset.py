"""Repository-specific MVP evaluation dataset schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Mapping


EVALUATION_DATASET_SCHEMA_VERSION = 1


class EvaluationScenario(StrEnum):
    """Coverage categories required by the MVP dataset."""

    IMPLEMENTATION_RATIONALE = "implementation_rationale"
    CHANGE_RISK = "change_risk"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    MULTIPLE_CANDIDATES = "multiple_candidates"
    FALSE_WARNING = "false_warning"


class RiskLabel(StrEnum):
    """Expected risk judgement for risk-oriented cases."""

    RISK_FOUND = "risk_found"
    NO_RISK_FOUND = "no_risk_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExpectedTarget:
    """Target that a resolver or evaluator should identify."""

    repository_id: str
    target_type: str
    artifact_ids: tuple[str, ...]
    file_path: str | None = None
    symbol_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_ids", tuple(self.artifact_ids))
        if not self.repository_id:
            raise EvaluationDatasetViolation("repository_id must be non-empty")
        if not self.target_type:
            raise EvaluationDatasetViolation("target_type must be non-empty")
        if not self.artifact_ids:
            raise EvaluationDatasetViolation("artifact_ids must be non-empty")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["artifact_ids"] = list(self.artifact_ids)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class EvaluationRecord:
    """One reviewed repository-specific evaluation case."""

    schema_version: int
    record_id: str
    source_repository: str
    scenario: EvaluationScenario
    question: str
    expected_target: ExpectedTarget
    required_evidence_ids: tuple[str, ...]
    allowed_inferences: tuple[str, ...]
    risk_label: RiskLabel
    split: str
    notes: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_evidence_ids", tuple(self.required_evidence_ids))
        object.__setattr__(self, "allowed_inferences", tuple(self.allowed_inferences))
        validate_evaluation_record(self)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "source_repository": self.source_repository,
            "scenario": self.scenario.value,
            "question": self.question,
            "expected_target": self.expected_target.to_dict(),
            "required_evidence_ids": list(self.required_evidence_ids),
            "allowed_inferences": list(self.allowed_inferences),
            "risk_label": self.risk_label.value,
            "split": self.split,
            "notes": self.notes,
            "metadata": dict(self.metadata),
        }


class EvaluationDatasetViolation(ValueError):
    """Raised when evaluation data can leak or cannot be evaluated."""


def validate_evaluation_record(record: EvaluationRecord) -> None:
    """Validate one reviewed evaluation record."""

    if record.schema_version != EVALUATION_DATASET_SCHEMA_VERSION:
        raise EvaluationDatasetViolation("unsupported evaluation schema_version")
    for field_name in ("record_id", "source_repository", "question", "split"):
        if not getattr(record, field_name):
            raise EvaluationDatasetViolation(f"{field_name} must be non-empty")
    if record.split not in {"train", "validation", "test"}:
        raise EvaluationDatasetViolation("split must be train, validation, or test")
    if record.source_repository != record.expected_target.repository_id:
        raise EvaluationDatasetViolation("source_repository must match expected_target.repository_id")
    if record.scenario in {
        EvaluationScenario.IMPLEMENTATION_RATIONALE,
        EvaluationScenario.CHANGE_RISK,
    } and not record.required_evidence_ids:
        raise EvaluationDatasetViolation("answerable cases must list required_evidence_ids")
    if record.scenario is EvaluationScenario.INSUFFICIENT_EVIDENCE and record.risk_label is not RiskLabel.UNKNOWN:
        raise EvaluationDatasetViolation("insufficient evidence cases must use unknown risk_label")


def load_evaluation_jsonl(path: Path) -> tuple[EvaluationRecord, ...]:
    """Load reviewed evaluation data from a JSONL file."""

    records: list[EvaluationRecord] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(evaluation_record_from_mapping(json.loads(line)))
        except Exception as error:
            raise EvaluationDatasetViolation(f"{path}:{line_number}: {error}") from error
    return tuple(records)


def evaluation_record_from_mapping(raw: Mapping[str, Any]) -> EvaluationRecord:
    """Convert a plain mapping into a validated record."""

    return EvaluationRecord(
        schema_version=_require_int(raw, "schema_version"),
        record_id=_require_str(raw, "record_id"),
        source_repository=_require_str(raw, "source_repository"),
        scenario=EvaluationScenario(_require_str(raw, "scenario")),
        question=_require_str(raw, "question"),
        expected_target=_target_from_mapping(_require_mapping(raw, "expected_target")),
        required_evidence_ids=tuple(_str_list(raw.get("required_evidence_ids", ()), "required_evidence_ids")),
        allowed_inferences=tuple(_str_list(raw.get("allowed_inferences", ()), "allowed_inferences")),
        risk_label=RiskLabel(_require_str(raw, "risk_label")),
        split=_require_str(raw, "split"),
        notes=str(raw.get("notes", "")),
        metadata=_mapping_or_empty(raw.get("metadata", {}), "metadata"),
    )


def validate_dataset_coverage(records: tuple[EvaluationRecord, ...]) -> None:
    """Require MVP edge cases that separate retrieval and generation failures."""

    scenarios = {record.scenario for record in records}
    required = {
        EvaluationScenario.IMPLEMENTATION_RATIONALE,
        EvaluationScenario.CHANGE_RISK,
        EvaluationScenario.INSUFFICIENT_EVIDENCE,
        EvaluationScenario.MULTIPLE_CANDIDATES,
        EvaluationScenario.FALSE_WARNING,
    }
    missing = required - scenarios
    if missing:
        missing_text = ", ".join(sorted(item.value for item in missing))
        raise EvaluationDatasetViolation(f"dataset is missing required scenarios: {missing_text}")


def _target_from_mapping(raw: Mapping[str, Any]) -> ExpectedTarget:
    return ExpectedTarget(
        repository_id=_require_str(raw, "repository_id"),
        target_type=_require_str(raw, "target_type"),
        artifact_ids=tuple(_str_list(raw.get("artifact_ids", ()), "artifact_ids")),
        file_path=raw.get("file_path"),
        symbol_name=raw.get("symbol_name"),
    )


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise EvaluationDatasetViolation(f"{key} must be a non-empty string")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int):
        raise EvaluationDatasetViolation(f"{key} must be an integer")
    return value


def _require_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise EvaluationDatasetViolation(f"{key} must be an object")
    return value


def _str_list(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not all(isinstance(item, str) and item for item in value):
        raise EvaluationDatasetViolation(f"{key} must be a list of non-empty strings")
    return tuple(value)


def _mapping_or_empty(value: Any, key: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvaluationDatasetViolation(f"{key} must be an object")
    return value
