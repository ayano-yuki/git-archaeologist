"""Common event schema for normalized repository history.

Common events are the stable contract between raw collectors, normalizers,
event graph construction, search, and Evidence Packs. The schema separates
directly observed fields from extracted and inferred fields so later stages can
avoid treating guesses as raw facts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
import re
from typing import Any, Mapping


COMMON_EVENT_SCHEMA_VERSION = 1

_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


class EventKind(StrEnum):
    """Repository history events that share the normalizer contract."""

    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    REVIEW = "review"
    CI = "ci"
    REVERT = "revert"


class EvidenceKind(StrEnum):
    """Raw evidence source used to create or support an event."""

    GIT_COMMIT = "git_commit"
    GIT_DIFF = "git_diff"
    GIT_BLAME = "git_blame"
    GITHUB_PULL_REQUEST = "github_pull_request"
    GITHUB_ISSUE = "github_issue"
    GITHUB_REVIEW = "github_review"
    GITHUB_COMMENT = "github_comment"
    GITHUB_ACTIONS_RUN = "github_actions_run"
    RAW_ARCHIVE = "raw_archive"
    HUMAN_ANNOTATION = "human_annotation"


class RelationKind(StrEnum):
    """Allowed graph edge meanings between common events."""

    MENTIONS = "mentions"
    CLOSES = "closes"
    IMPLEMENTS = "implements"
    REVIEWS = "reviews"
    TRIGGERS = "triggers"
    FAILS = "fails"
    FIXES = "fixes"
    REVERTS = "reverts"
    DUPLICATES = "duplicates"
    DERIVED_FROM = "derived_from"
    POSSIBLY_RELATED = "possibly_related"


@dataclass(frozen=True)
class EventFieldSet:
    """Fields that may be observed, extracted, or inferred.

    The same names are intentionally available in each provenance bucket. For
    example, a PR number may be observed from GitHub API payloads, extracted
    from a merge commit message, or inferred from a nearby branch name.
    """

    occurred_at: str | None = None
    actor: str | None = None
    commit_sha: str | None = None
    pull_request_number: int | None = None
    issue_number: int | None = None
    file_path: str | None = None
    symbol_name: str | None = None
    diff_hunk: str | None = None
    title: str | None = None
    body: str | None = None

    def validate(self, *, require_observed_time: bool = False) -> None:
        if require_observed_time and not self.occurred_at:
            raise ValueError("observed.occurred_at must be a non-empty ISO timestamp")
        if self.occurred_at:
            _validate_iso_datetime(self.occurred_at, "occurred_at")
        if self.commit_sha and not _SHA_RE.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a 7 to 40 character hex SHA")
        if self.pull_request_number is not None and self.pull_request_number < 1:
            raise ValueError("pull_request_number must be positive")
        if self.issue_number is not None and self.issue_number < 1:
            raise ValueError("issue_number must be positive")
        for key in ("actor", "file_path", "symbol_name", "diff_hunk", "title", "body"):
            value = getattr(self, key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be a string when present")

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class ArtifactReference:
    """Pointer back to a raw archive item or external artifact."""

    artifact_kind: EvidenceKind
    artifact_id: str
    source_url: str
    raw_path: str | None = None
    content_hash: str | None = None

    def validate(self) -> None:
        if not self.artifact_id:
            raise ValueError("artifact_reference.artifact_id must be non-empty")
        _validate_url(self.source_url, "artifact_reference.source_url")
        if self.raw_path is not None and not self.raw_path:
            raise ValueError("artifact_reference.raw_path must be non-empty")
        if self.content_hash is not None and not self.content_hash:
            raise ValueError("artifact_reference.content_hash must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(
            {
                "artifact_kind": self.artifact_kind.value,
                "artifact_id": self.artifact_id,
                "source_url": self.source_url,
                "raw_path": self.raw_path,
                "content_hash": self.content_hash,
            }
        )


@dataclass(frozen=True)
class EventRelation:
    """Directed relation from one event to another."""

    relation_kind: RelationKind
    target_event_id: str
    evidence_kind: EvidenceKind
    confidence: float = 1.0
    source_url: str | None = None
    rationale: str | None = None
    inferred: bool = False

    def validate(self) -> None:
        if not self.target_event_id:
            raise ValueError("relation.target_event_id must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("relation.confidence must be between 0.0 and 1.0")
        if self.source_url is not None:
            _validate_url(self.source_url, "relation.source_url")
        if self.inferred and self.confidence >= 1.0:
            raise ValueError("inferred relations must use confidence below 1.0")

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(
            {
                "relation_kind": self.relation_kind.value,
                "target_event_id": self.target_event_id,
                "evidence_kind": self.evidence_kind.value,
                "confidence": self.confidence,
                "source_url": self.source_url,
                "rationale": self.rationale,
                "inferred": self.inferred,
            }
        )


@dataclass(frozen=True)
class CommonEvent:
    """Versioned event schema shared by collectors and normalizers."""

    event_id: str
    kind: EventKind
    source_url: str
    observed: EventFieldSet
    artifact_references: tuple[ArtifactReference, ...]
    evidence_kind: EvidenceKind
    extracted: EventFieldSet = field(default_factory=EventFieldSet)
    inferred: EventFieldSet = field(default_factory=EventFieldSet)
    relations: tuple[EventRelation, ...] = ()
    schema_version: int = COMMON_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_references", tuple(self.artifact_references))
        object.__setattr__(self, "relations", tuple(self.relations))
        self.validate()

    def validate(self) -> None:
        if self.schema_version != COMMON_EVENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported common event schema_version: {self.schema_version}")
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        _validate_url(self.source_url, "source_url")
        self.observed.validate(require_observed_time=True)
        self.extracted.validate()
        self.inferred.validate()
        if not self.artifact_references:
            raise ValueError("artifact_references must not be empty")
        for reference in self.artifact_references:
            reference.validate()
        for relation in self.relations:
            relation.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "kind": self.kind.value,
            "source_url": self.source_url,
            "evidence_kind": self.evidence_kind.value,
            "observed": self.observed.to_dict(),
            "extracted": self.extracted.to_dict(),
            "inferred": self.inferred.to_dict(),
            "artifact_references": [
                reference.to_dict() for reference in self.artifact_references
            ],
            "relations": [relation.to_dict() for relation in self.relations],
        }


@dataclass(frozen=True)
class ConversionFailureReport:
    """Human-facing report for artifacts that cannot become common events."""

    repository_id: str
    artifact_kind: EvidenceKind
    target: str
    operation: str
    error_type: str
    error_message: str
    source_url: str
    quarantine_path: str
    retry_count: int = 0

    def validate(self) -> None:
        _require_non_empty(self.repository_id, "repository_id")
        _require_non_empty(self.target, "target")
        _require_non_empty(self.operation, "operation")
        _require_non_empty(self.error_type, "error_type")
        _require_non_empty(self.error_message, "error_message")
        _validate_url(self.source_url, "source_url")
        _require_non_empty(self.quarantine_path, "quarantine_path")
        if self.retry_count < 0:
            raise ValueError("retry_count must be zero or positive")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "repository_id": self.repository_id,
            "artifact_kind": self.artifact_kind.value,
            "target": self.target,
            "operation": self.operation,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "source_url": self.source_url,
            "quarantine_path": self.quarantine_path,
            "retry_count": self.retry_count,
        }


def validate_common_event(raw_event: Mapping[str, Any]) -> CommonEvent:
    """Validate a mapping and return a typed CommonEvent."""

    schema_version = _require_int(raw_event, "schema_version")
    event = CommonEvent(
        schema_version=schema_version,
        event_id=_require_str(raw_event, "event_id"),
        kind=EventKind(_require_str(raw_event, "kind")),
        source_url=_require_str(raw_event, "source_url"),
        evidence_kind=EvidenceKind(_require_str(raw_event, "evidence_kind")),
        observed=_field_set_from_mapping(_require_mapping(raw_event, "observed")),
        extracted=_field_set_from_mapping(raw_event.get("extracted", {})),
        inferred=_field_set_from_mapping(raw_event.get("inferred", {})),
        artifact_references=tuple(
            _artifact_reference_from_mapping(item)
            for item in _require_mapping_sequence(raw_event, "artifact_references")
        ),
        relations=tuple(
            _relation_from_mapping(item)
            for item in _mapping_sequence(raw_event.get("relations", ()), "relations")
        ),
    )
    return event


def build_conversion_failure_report(
    *,
    repository_id: str,
    artifact_kind: EvidenceKind,
    target: str,
    operation: str,
    error: Exception,
    source_url: str,
    quarantine_path: str,
    retry_count: int = 0,
) -> ConversionFailureReport:
    """Create the human report payload for an isolated conversion failure."""

    report = ConversionFailureReport(
        repository_id=repository_id,
        artifact_kind=artifact_kind,
        target=target,
        operation=operation,
        error_type=type(error).__name__,
        error_message=str(error),
        source_url=source_url,
        quarantine_path=quarantine_path,
        retry_count=retry_count,
    )
    report.validate()
    return report


def _field_set_from_mapping(raw: Mapping[str, Any]) -> EventFieldSet:
    return EventFieldSet(
        occurred_at=_optional_str(raw, "occurred_at"),
        actor=_optional_str(raw, "actor"),
        commit_sha=_optional_str(raw, "commit_sha"),
        pull_request_number=_optional_int(raw, "pull_request_number"),
        issue_number=_optional_int(raw, "issue_number"),
        file_path=_optional_str(raw, "file_path"),
        symbol_name=_optional_str(raw, "symbol_name"),
        diff_hunk=_optional_str(raw, "diff_hunk"),
        title=_optional_str(raw, "title"),
        body=_optional_str(raw, "body"),
    )


def _artifact_reference_from_mapping(raw: Mapping[str, Any]) -> ArtifactReference:
    return ArtifactReference(
        artifact_kind=EvidenceKind(_require_str(raw, "artifact_kind")),
        artifact_id=_require_str(raw, "artifact_id"),
        source_url=_require_str(raw, "source_url"),
        raw_path=_optional_str(raw, "raw_path"),
        content_hash=_optional_str(raw, "content_hash"),
    )


def _relation_from_mapping(raw: Mapping[str, Any]) -> EventRelation:
    return EventRelation(
        relation_kind=RelationKind(_require_str(raw, "relation_kind")),
        target_event_id=_require_str(raw, "target_event_id"),
        evidence_kind=EvidenceKind(_require_str(raw, "evidence_kind")),
        confidence=_optional_float(raw, "confidence", default=1.0),
        source_url=_optional_str(raw, "source_url"),
        rationale=_optional_str(raw, "rationale"),
        inferred=_optional_bool(raw, "inferred", default=False),
    )


def _validate_iso_datetime(value: str, field_name: str) -> None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO timestamp") from exc


def _validate_url(value: str, field_name: str) -> None:
    if not value.startswith(("https://", "http://")):
        raise ValueError(f"{field_name} must be an http or https URL")


def _drop_none(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if value is not None}


def _require_mapping_sequence(raw: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    return _mapping_sequence(_require(raw, key), key)


def _mapping_sequence(value: Any, key: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list | tuple) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{key} must be a list of objects")
    return tuple(value)


def _require_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = _require(raw, key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = _require(raw, key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_str(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string when present")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    value = _require(raw, key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_int(raw: Mapping[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer when present")
    return value


def _optional_float(raw: Mapping[str, Any], key: str, *, default: float) -> float:
    value = raw.get(key, default)
    if not isinstance(value, int | float):
        raise ValueError(f"{key} must be a number when present")
    return float(value)


def _optional_bool(raw: Mapping[str, Any], key: str, *, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean when present")
    return value


def _require(raw: Mapping[str, Any], key: str) -> Any:
    if key not in raw:
        raise ValueError(f"missing required field: {key}")
    return raw[key]


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
