"""Incremental sync state and index generation safeguards."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ArtifactSyncKind(StrEnum):
    """Artifact types tracked by Phase2 incremental sync."""

    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    REVIEW = "review"
    CI_RUN = "ci_run"


@dataclass(frozen=True)
class SyncWatermark:
    """Latest known state for one artifact stream."""

    artifact_kind: ArtifactSyncKind
    updated_at: str
    cursor: str | None = None
    head_sha: str | None = None


@dataclass(frozen=True)
class ArtifactUpdate:
    """Candidate artifact observed during a sync."""

    artifact_kind: ArtifactSyncKind
    artifact_id: str
    updated_at: str
    cursor: str | None = None
    head_sha: str | None = None
    deleted: bool = False

    def __post_init__(self) -> None:
        if not self.artifact_id:
            raise ValueError("artifact_id must be non-empty")
        if not self.updated_at:
            raise ValueError("updated_at must be non-empty")


@dataclass(frozen=True)
class SyncState:
    """Repository sync state published with an index version."""

    repository_id: str
    index_version: str
    synced_at: str
    watermarks: tuple[SyncWatermark, ...]
    tombstones: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "watermarks", tuple(self.watermarks))
        object.__setattr__(self, "tombstones", tuple(self.tombstones))
        if not self.repository_id:
            raise ValueError("repository_id must be non-empty")
        if not self.index_version:
            raise ValueError("index_version must be non-empty")

    def watermark_for(self, artifact_kind: ArtifactSyncKind) -> SyncWatermark | None:
        return next((mark for mark in self.watermarks if mark.artifact_kind is artifact_kind), None)


@dataclass(frozen=True)
class IncrementalSyncPlan:
    """Updates selected for processing in one incremental sync."""

    updates: tuple[ArtifactUpdate, ...]
    skipped_artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "updates", tuple(self.updates))
        object.__setattr__(self, "skipped_artifact_ids", tuple(self.skipped_artifact_ids))


def plan_incremental_sync(state: SyncState, observed_updates: tuple[ArtifactUpdate, ...]) -> IncrementalSyncPlan:
    """Select only changed artifacts, including deleted and force-pushed artifacts."""

    selected: list[ArtifactUpdate] = []
    skipped: list[str] = []
    seen: set[tuple[ArtifactSyncKind, str]] = set()
    for update in observed_updates:
        key = (update.artifact_kind, update.artifact_id)
        if key in seen:
            skipped.append(update.artifact_id)
            continue
        seen.add(key)
        watermark = state.watermark_for(update.artifact_kind)
        changed_by_time = watermark is None or update.updated_at > watermark.updated_at
        changed_by_head = update.head_sha is not None and watermark is not None and update.head_sha != watermark.head_sha
        if update.deleted or changed_by_time or changed_by_head:
            selected.append(update)
        else:
            skipped.append(update.artifact_id)
    return IncrementalSyncPlan(updates=tuple(selected), skipped_artifact_ids=tuple(skipped))


def apply_sync_success(
    state: SyncState,
    processed_updates: tuple[ArtifactUpdate, ...],
    *,
    new_index_version: str,
    synced_at: str,
) -> SyncState:
    """Publish a new sync state after all selected updates are processed."""

    if not processed_updates:
        return SyncState(
            repository_id=state.repository_id,
            index_version=new_index_version,
            synced_at=synced_at,
            watermarks=state.watermarks,
            tombstones=state.tombstones,
        )

    marks = {mark.artifact_kind: mark for mark in state.watermarks}
    tombstones = set(state.tombstones)
    for update in processed_updates:
        current = marks.get(update.artifact_kind)
        if current is None or update.updated_at >= current.updated_at:
            marks[update.artifact_kind] = SyncWatermark(
                artifact_kind=update.artifact_kind,
                updated_at=update.updated_at,
                cursor=update.cursor,
                head_sha=update.head_sha,
            )
        if update.deleted:
            tombstones.add(update.artifact_id)

    return SyncState(
        repository_id=state.repository_id,
        index_version=new_index_version,
        synced_at=synced_at,
        watermarks=tuple(sorted(marks.values(), key=lambda mark: mark.artifact_kind.value)),
        tombstones=tuple(sorted(tombstones)),
    )
