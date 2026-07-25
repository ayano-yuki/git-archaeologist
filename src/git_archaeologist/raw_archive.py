"""Raw Archive storage primitives.

Raw Archive stores source artifacts before normalization so every derived event
can be traced back to immutable bytes, a content hash, and the source URL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote


RAW_ARCHIVE_SCHEMA_VERSION = 1
RAW_ARCHIVE_HASH_ALGORITHM = "sha256"
RAW_ARCHIVE_DEFAULT_EXTENSION = "json"
REDACTED_SECRET_MARKER = "[REDACTED:secret]"
SUPPRESSED_SECRET_MARKER = "[SUPPRESSED:secret]"

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


@dataclass(frozen=True)
class RedactionMarkers:
    """Redaction metadata attached to a stored raw artifact."""

    redacted_labels: tuple[str, ...] = ()
    suppressed_fields: tuple[str, ...] = ()

    @property
    def has_redactions(self) -> bool:
        return bool(self.redacted_labels or self.suppressed_fields)

    def to_dict(self) -> dict[str, object]:
        return {
            "has_redactions": self.has_redactions,
            "redacted_labels": list(self.redacted_labels),
            "suppressed_fields": list(self.suppressed_fields),
            "redacted_markers": [
                redacted_secret_marker(label) for label in self.redacted_labels
            ],
            "suppressed_markers": [
                suppressed_secret_marker(field_name)
                for field_name in self.suppressed_fields
            ],
        }


@dataclass(frozen=True)
class RawArtifact:
    """Artifact bytes and identity used to save immutable raw data."""

    repository_id: str
    artifact_kind: str
    external_id: str
    content: bytes
    source_url: str
    retrieved_at: datetime
    content_type: str = "application/json"
    redaction: RedactionMarkers = field(default_factory=RedactionMarkers)


@dataclass(frozen=True)
class RawArchiveManifestRecord:
    """Versioned manifest row for one Raw Archive artifact."""

    schema_version: int
    repository_id: str
    artifact_kind: str
    external_id: str
    source_url: str
    retrieved_at: datetime
    archive_path: str
    content_hash: str
    byte_size: int
    content_type: str
    redaction: RedactionMarkers

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "repository_id": self.repository_id,
            "artifact_kind": self.artifact_kind,
            "external_id": self.external_id,
            "source_url": self.source_url,
            "retrieved_at": _format_datetime(self.retrieved_at),
            "archive_path": self.archive_path,
            "content_hash": self.content_hash,
            "byte_size": self.byte_size,
            "content_type": self.content_type,
            "redaction": self.redaction.to_dict(),
        }


@dataclass(frozen=True)
class RawArchiveSaveResult:
    """Result of saving a raw artifact."""

    manifest_record: RawArchiveManifestRecord
    content_path: Path
    wrote_content: bool
    duplicate: bool


class RawArchiveStorageError(RuntimeError):
    """Storage error with a human-safe report payload."""

    def __init__(
        self,
        *,
        repository_id: str,
        artifact_kind: str,
        target: str,
        operation: str,
        error_type: str,
        error_message: str,
        source_url: str = "",
        retry_count: int = 0,
    ) -> None:
        super().__init__(error_message)
        self.repository_id = repository_id
        self.artifact_kind = artifact_kind
        self.target = target
        self.operation = operation
        self.error_type = error_type
        self.error_message = error_message
        self.source_url = source_url
        self.retry_count = retry_count

    def human_payload(self) -> dict[str, object]:
        return error_report_payload(
            repository_id=self.repository_id,
            artifact_kind=self.artifact_kind,
            target=self.target,
            operation=self.operation,
            error_type=self.error_type,
            error_message=self.error_message,
            source_url=self.source_url,
            retry_count=self.retry_count,
        )


def canonical_json_bytes(raw: Mapping[str, Any]) -> bytes:
    """Return stable UTF-8 JSON bytes for a raw JSON artifact."""

    return json.dumps(
        raw,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def content_hash(content: bytes) -> str:
    """Return a manifest-ready content hash string."""

    return f"{RAW_ARCHIVE_HASH_ALGORITHM}:{sha256(content).hexdigest()}"


def stable_artifact_path(
    repository_id: str,
    artifact_kind: str,
    external_id: str,
    *,
    extension: str = RAW_ARCHIVE_DEFAULT_EXTENSION,
) -> Path:
    """Return a deterministic relative path for a repository artifact."""

    owner, name = _repository_segments(repository_id)
    artifact_segment = _safe_segment(artifact_kind, "artifact_kind")
    external_segment = _safe_segment(external_id, "external_id")
    extension_segment = _safe_extension(extension)
    return Path(owner) / name / artifact_segment / f"{external_segment}.{extension_segment}"


def build_manifest_record(
    artifact: RawArtifact,
    *,
    extension: str = RAW_ARCHIVE_DEFAULT_EXTENSION,
) -> RawArchiveManifestRecord:
    """Build the manifest record for an artifact without writing content."""

    archive_path = stable_artifact_path(
        artifact.repository_id,
        artifact.artifact_kind,
        artifact.external_id,
        extension=extension,
    ).as_posix()
    return RawArchiveManifestRecord(
        schema_version=RAW_ARCHIVE_SCHEMA_VERSION,
        repository_id=artifact.repository_id,
        artifact_kind=artifact.artifact_kind,
        external_id=artifact.external_id,
        source_url=artifact.source_url,
        retrieved_at=artifact.retrieved_at,
        archive_path=archive_path,
        content_hash=content_hash(artifact.content),
        byte_size=len(artifact.content),
        content_type=artifact.content_type,
        redaction=artifact.redaction,
    )


def save_raw_artifact(
    archive_root: str | Path,
    artifact: RawArtifact,
    *,
    extension: str = RAW_ARCHIVE_DEFAULT_EXTENSION,
) -> RawArchiveSaveResult:
    """Save artifact bytes once and return the manifest record.

    Saving the same artifact path with the same content is treated as a
    duplicate rerun. Saving the same path with different bytes is an integrity
    error because Raw Archive entries are immutable.
    """

    manifest_record = build_manifest_record(artifact, extension=extension)
    content_path = Path(archive_root) / manifest_record.archive_path
    expected_hash = manifest_record.content_hash

    if content_path.exists():
        actual_hash = content_hash(content_path.read_bytes())
        if actual_hash != expected_hash:
            raise RawArchiveStorageError(
                repository_id=artifact.repository_id,
                artifact_kind=artifact.artifact_kind,
                target=artifact.external_id,
                operation="save_raw_artifact",
                error_type="storage_integrity_error",
                error_message=(
                    "raw artifact path already exists with different content hash"
                ),
                source_url=artifact.source_url,
            )
        return RawArchiveSaveResult(
            manifest_record=manifest_record,
            content_path=content_path,
            wrote_content=False,
            duplicate=True,
        )

    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_bytes(artifact.content)
    return RawArchiveSaveResult(
        manifest_record=manifest_record,
        content_path=content_path,
        wrote_content=True,
        duplicate=False,
    )


def redacted_secret_marker(label: str = "secret") -> str:
    """Return a marker for a value redacted before Raw Archive storage."""

    return f"[REDACTED:{_marker_label(label)}]"


def suppressed_secret_marker(field_name: str = "secret") -> str:
    """Return a marker for a field withheld from storage and reports."""

    return f"[SUPPRESSED:{_marker_label(field_name)}]"


def error_report_payload(
    *,
    repository_id: str,
    artifact_kind: str,
    target: str,
    operation: str,
    error_type: str,
    error_message: str,
    source_url: str = "",
    retry_count: int = 0,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    """Build a human-safe collection error payload."""

    payload: dict[str, object] = {
        "repository_id": repository_id,
        "artifact_kind": artifact_kind,
        "target": target,
        "operation": operation,
        "error_type": error_type,
        "error_message": error_message,
        "source_url": source_url,
        "retry_count": retry_count,
        "suppressed_fields": list(HUMAN_ERROR_SUPPRESSED_FIELDS),
    }
    if extra:
        for key, value in extra.items():
            if key not in HUMAN_ERROR_SUPPRESSED_FIELDS:
                payload[key] = value
    return payload


def _repository_segments(repository_id: str) -> tuple[str, str]:
    segments = repository_id.split("/")
    if len(segments) != 2:
        raise ValueError("repository_id must be in owner/name form")
    return (
        _safe_segment(segments[0], "repository owner"),
        _safe_segment(segments[1], "repository name"),
    )


def _safe_segment(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if value in {".", ".."}:
        raise ValueError(f"{field_name} must not be a path traversal segment")
    return quote(value, safe="-._~")


def _safe_extension(extension: str) -> str:
    if not extension or "/" in extension or "\\" in extension or extension in {".", ".."}:
        raise ValueError("extension must be a safe file extension")
    return extension.lstrip(".")


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _marker_label(value: str) -> str:
    if not value:
        raise ValueError("marker label must be a non-empty string")
    return value.replace("]", "_")
