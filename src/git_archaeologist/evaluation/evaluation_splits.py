"""Decision-level split manifest for leakage-resistant evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Mapping


SPLIT_MANIFEST_SCHEMA_VERSION = 1


class EvaluationSplit(StrEnum):
    """Dataset split names."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


@dataclass(frozen=True)
class SplitWindow:
    """Optional chronological window used for temporal evaluation."""

    start: date
    end: date

    def validate(self) -> None:
        if self.end < self.start:
            raise SplitManifestViolation("split window end must not be before start")


@dataclass(frozen=True)
class DecisionSplit:
    """One split entry grouped by decision, not raw artifact."""

    split: EvaluationSplit
    decision_ids: tuple[str, ...]
    artifact_ids: tuple[str, ...]
    reason: str
    window: SplitWindow | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_ids", tuple(self.decision_ids))
        object.__setattr__(self, "artifact_ids", tuple(self.artifact_ids))
        self.validate()

    def validate(self) -> None:
        if not self.decision_ids:
            raise SplitManifestViolation("decision_ids must be non-empty")
        if not self.artifact_ids:
            raise SplitManifestViolation("artifact_ids must be non-empty")
        if not self.reason:
            raise SplitManifestViolation("split reason must be non-empty")
        if self.window is not None:
            self.window.validate()


@dataclass(frozen=True)
class EvaluationSplitManifest:
    """Reviewed split manifest for SFT and repeatable evaluation."""

    schema_version: int
    dataset_version: str
    source_repository: str
    entries: tuple[DecisionSplit, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))
        validate_split_manifest(self)


class SplitManifestViolation(ValueError):
    """Raised when split data would permit leakage."""


def validate_split_manifest(manifest: EvaluationSplitManifest) -> None:
    """Validate required splits and no decision/artifact overlap."""

    if manifest.schema_version != SPLIT_MANIFEST_SCHEMA_VERSION:
        raise SplitManifestViolation("unsupported split manifest schema_version")
    if not manifest.dataset_version:
        raise SplitManifestViolation("dataset_version must be non-empty")
    if not manifest.source_repository:
        raise SplitManifestViolation("source_repository must be non-empty")

    present_splits = {entry.split for entry in manifest.entries}
    required_splits = {EvaluationSplit.TRAIN, EvaluationSplit.VALIDATION, EvaluationSplit.TEST}
    if missing := required_splits - present_splits:
        missing_text = ", ".join(sorted(split.value for split in missing))
        raise SplitManifestViolation(f"manifest is missing split entries: {missing_text}")

    _validate_no_overlap(manifest.entries, field_name="decision_ids")
    _validate_no_overlap(manifest.entries, field_name="artifact_ids")


def load_split_manifest(path: Path) -> EvaluationSplitManifest:
    """Load a reviewed split manifest from JSON."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise SplitManifestViolation("split manifest must be a JSON object")
    return split_manifest_from_mapping(raw)


def split_manifest_from_mapping(raw: Mapping[str, Any]) -> EvaluationSplitManifest:
    """Convert a plain mapping into a validated split manifest."""

    return EvaluationSplitManifest(
        schema_version=_require_int(raw, "schema_version"),
        dataset_version=_require_str(raw, "dataset_version"),
        source_repository=_require_str(raw, "source_repository"),
        entries=tuple(_entry_from_mapping(item) for item in _mapping_list(raw.get("entries", ()), "entries")),
    )


def _entry_from_mapping(raw: Mapping[str, Any]) -> DecisionSplit:
    window = raw.get("window")
    return DecisionSplit(
        split=EvaluationSplit(_require_str(raw, "split")),
        decision_ids=tuple(_str_list(raw.get("decision_ids", ()), "decision_ids")),
        artifact_ids=tuple(_str_list(raw.get("artifact_ids", ()), "artifact_ids")),
        reason=_require_str(raw, "reason"),
        window=_window_from_mapping(window) if window is not None else None,
    )


def _window_from_mapping(raw: Any) -> SplitWindow:
    if not isinstance(raw, Mapping):
        raise SplitManifestViolation("window must be an object")
    return SplitWindow(
        start=date.fromisoformat(_require_str(raw, "start")),
        end=date.fromisoformat(_require_str(raw, "end")),
    )


def _validate_no_overlap(entries: tuple[DecisionSplit, ...], *, field_name: str) -> None:
    seen: dict[str, EvaluationSplit] = {}
    for entry in entries:
        for value in getattr(entry, field_name):
            previous = seen.get(value)
            if previous is not None and previous is not entry.split:
                raise SplitManifestViolation(f"{field_name} value crosses splits: {value}")
            seen[value] = entry.split


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise SplitManifestViolation(f"{key} must be a non-empty string")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int):
        raise SplitManifestViolation(f"{key} must be an integer")
    return value


def _mapping_list(value: Any, key: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list | tuple) or not all(isinstance(item, Mapping) for item in value):
        raise SplitManifestViolation(f"{key} must be a list of objects")
    return tuple(value)


def _str_list(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not all(isinstance(item, str) and item for item in value):
        raise SplitManifestViolation(f"{key} must be a list of non-empty strings")
    return tuple(value)
