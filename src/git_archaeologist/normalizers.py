"""Artifact normalizers that convert raw records into common events."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Protocol

from git_archaeologist.common_events import (
    ArtifactReference,
    CommonEvent,
    EventFieldSet,
    EventKind,
    EvidenceKind,
    build_conversion_failure_report,
)


NORMALIZER_OPERATION = "normalize_common_event"


@dataclass(frozen=True)
class RawArtifactEnvelope:
    """Raw artifact plus the provenance needed to normalize it."""

    repository_id: str
    artifact_kind: EvidenceKind
    artifact_id: str
    source_url: str
    raw: Mapping[str, Any]
    raw_path: str | None = None
    content_hash: str | None = None


@dataclass(frozen=True)
class NormalizationSuccess:
    """Successful normalized event result."""

    event: CommonEvent

    @property
    def event_id(self) -> str:
        return self.event.event_id


@dataclass(frozen=True)
class NormalizationFailure:
    """Failed normalization result with quarantine metadata."""

    artifact: RawArtifactEnvelope
    reason: str
    quarantine_path: str

    def human_payload(self) -> dict[str, object]:
        return build_conversion_failure_report(
            repository_id=self.artifact.repository_id,
            artifact_kind=self.artifact.artifact_kind,
            target=self.artifact.artifact_id,
            operation=NORMALIZER_OPERATION,
            error=ValueError(self.reason),
            source_url=self.artifact.source_url,
            quarantine_path=self.quarantine_path,
        ).to_dict()


class ArtifactNormalizer(Protocol):
    """Normalizer interface implemented per artifact family."""

    artifact_kind: EvidenceKind

    def normalize(self, artifact: RawArtifactEnvelope) -> NormalizationSuccess:
        """Normalize one raw artifact or raise ValueError."""


class GenericArtifactNormalizer:
    """Mapping-based normalizer for the MVP artifact kinds."""

    def __init__(self, artifact_kind: EvidenceKind) -> None:
        self.artifact_kind = artifact_kind

    def normalize(self, artifact: RawArtifactEnvelope) -> NormalizationSuccess:
        if artifact.artifact_kind != self.artifact_kind:
            raise ValueError(
                f"normalizer for {self.artifact_kind.value} cannot handle {artifact.artifact_kind.value}"
            )

        kind = _event_kind_for(artifact.artifact_kind)
        observed = _observed_fields(artifact.artifact_kind, artifact.raw)
        event = CommonEvent(
            event_id=stable_event_id(artifact),
            kind=kind,
            source_url=artifact.source_url,
            evidence_kind=artifact.artifact_kind,
            observed=observed,
            artifact_references=(
                ArtifactReference(
                    artifact_kind=artifact.artifact_kind,
                    artifact_id=artifact.artifact_id,
                    source_url=artifact.source_url,
                    raw_path=artifact.raw_path,
                    content_hash=artifact.content_hash,
                ),
            ),
        )
        return NormalizationSuccess(event=event)


def normalize_artifact(
    artifact: RawArtifactEnvelope,
    *,
    normalizers: Mapping[EvidenceKind, ArtifactNormalizer] | None = None,
    quarantine_root: str = "data/quarantine",
) -> NormalizationSuccess | NormalizationFailure:
    """Normalize one artifact and return success or failure explicitly."""

    registry = normalizers or default_normalizers()
    normalizer = registry.get(artifact.artifact_kind)
    if normalizer is None:
        return _failure(
            artifact,
            reason=f"unsupported artifact kind: {artifact.artifact_kind.value}",
            quarantine_root=quarantine_root,
        )

    try:
        return normalizer.normalize(artifact)
    except Exception as exc:
        return _failure(artifact, reason=str(exc), quarantine_root=quarantine_root)


def default_normalizers() -> dict[EvidenceKind, ArtifactNormalizer]:
    """Return MVP artifact normalizers."""

    kinds = (
        EvidenceKind.GITHUB_PULL_REQUEST,
        EvidenceKind.GITHUB_ISSUE,
        EvidenceKind.GITHUB_REVIEW,
        EvidenceKind.GITHUB_COMMENT,
        EvidenceKind.GIT_COMMIT,
        EvidenceKind.GITHUB_ACTIONS_RUN,
    )
    return {kind: GenericArtifactNormalizer(kind) for kind in kinds}


def stable_event_id(artifact: RawArtifactEnvelope) -> str:
    """Generate a stable event ID from repository, kind, and raw artifact ID."""

    digest = sha256(
        f"{artifact.repository_id}\0{artifact.artifact_kind.value}\0{artifact.artifact_id}".encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return f"event-{artifact.artifact_kind.value}-{digest}"


def _observed_fields(
    artifact_kind: EvidenceKind,
    raw: Mapping[str, Any],
) -> EventFieldSet:
    occurred_at = _first_str(
        raw,
        "createdAt",
        "created_at",
        "author_date",
        "committer_date",
        "updatedAt",
        "updated_at",
    )
    if not occurred_at:
        raise ValueError("missing observed timestamp")

    return EventFieldSet(
        occurred_at=occurred_at,
        actor=_actor(raw),
        commit_sha=_optional_str(raw, "commit_sha", "sha", "headSha"),
        pull_request_number=_optional_int(raw, "pull_request_number", "number")
        if artifact_kind in {EvidenceKind.GITHUB_PULL_REQUEST, EvidenceKind.GITHUB_REVIEW}
        else None,
        issue_number=_optional_int(raw, "issue_number", "number")
        if artifact_kind == EvidenceKind.GITHUB_ISSUE
        else None,
        file_path=_optional_str(raw, "file_path", "path"),
        symbol_name=_optional_str(raw, "symbol_name"),
        diff_hunk=_optional_str(raw, "diff_hunk", "patch"),
        title=_optional_str(raw, "title", "subject", "displayTitle"),
        body=_optional_str(raw, "body", "message"),
    )


def _event_kind_for(artifact_kind: EvidenceKind) -> EventKind:
    mapping = {
        EvidenceKind.GITHUB_PULL_REQUEST: EventKind.PULL_REQUEST,
        EvidenceKind.GITHUB_ISSUE: EventKind.ISSUE,
        EvidenceKind.GITHUB_REVIEW: EventKind.REVIEW,
        EvidenceKind.GITHUB_COMMENT: EventKind.REVIEW,
        EvidenceKind.GIT_COMMIT: EventKind.COMMIT,
        EvidenceKind.GITHUB_ACTIONS_RUN: EventKind.CI,
    }
    try:
        return mapping[artifact_kind]
    except KeyError as exc:
        raise ValueError(f"unsupported artifact kind: {artifact_kind.value}") from exc


def _failure(
    artifact: RawArtifactEnvelope,
    *,
    reason: str,
    quarantine_root: str,
) -> NormalizationFailure:
    return NormalizationFailure(
        artifact=artifact,
        reason=reason,
        quarantine_path=f"{quarantine_root.rstrip('/')}/{artifact.artifact_kind.value}/{artifact.artifact_id}.json",
    )


def _actor(raw: Mapping[str, Any]) -> str | None:
    author = raw.get("author")
    if isinstance(author, Mapping):
        login = author.get("login") or author.get("name")
        if isinstance(login, str) and login:
            return login
    return _optional_str(raw, "actor", "author_name", "user")


def _first_str(raw: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _optional_str(raw: Mapping[str, Any], *keys: str) -> str | None:
    return _first_str(raw, *keys)


def _optional_int(raw: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, int):
            return value
    return None
