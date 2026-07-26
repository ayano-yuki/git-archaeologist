"""Phase5 sync status, manual sync planning, and scheduler configuration."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Sequence

from git_archaeologist.ops.incremental_sync import (
    ArtifactSyncKind,
    ArtifactUpdate,
    IncrementalSyncPlan,
    SyncState,
    SyncWatermark,
    plan_incremental_sync,
)


DEFAULT_INDEX_VERSION = "phase5-index-v1"
DEFAULT_SYNCED_AT = "1970-01-01T00:00:00+00:00"


@dataclass(frozen=True)
class SchedulerConfig:
    """Portable scheduler plan without installing an OS-level job."""

    enabled: bool
    interval_minutes: int
    command: str
    mutates_external_scheduler: bool = False

    def __post_init__(self) -> None:
        if self.interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Phase5SyncStatusReport:
    """Current published sync state for Phase5 local operation."""

    status: str
    repository_id: str
    index_version: str
    synced_at: str
    watermarks: tuple[dict[str, object], ...]
    tombstones: tuple[str, ...]
    scheduler: SchedulerConfig
    manual_sync_command: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "watermarks", tuple(self.watermarks))
        object.__setattr__(self, "tombstones", tuple(self.tombstones))

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "repository_id": self.repository_id,
            "index_version": self.index_version,
            "synced_at": self.synced_at,
            "watermarks": list(self.watermarks),
            "tombstones": list(self.tombstones),
            "scheduler": self.scheduler.to_dict(),
            "manual_sync_command": self.manual_sync_command,
        }


@dataclass(frozen=True)
class Phase5ManualSyncPlanReport:
    """Manual sync plan that does not collect or mutate remote data."""

    status: str
    repository_id: str
    index_version: str
    observed_update_count: int
    selected_updates: tuple[dict[str, object], ...]
    skipped_artifact_ids: tuple[str, ...]
    scheduler: SchedulerConfig
    external_collection_executed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_updates", tuple(self.selected_updates))
        object.__setattr__(self, "skipped_artifact_ids", tuple(self.skipped_artifact_ids))

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "repository_id": self.repository_id,
            "index_version": self.index_version,
            "observed_update_count": self.observed_update_count,
            "selected_updates": list(self.selected_updates),
            "skipped_artifact_ids": list(self.skipped_artifact_ids),
            "scheduler": self.scheduler.to_dict(),
            "external_collection_executed": self.external_collection_executed,
        }


def build_default_sync_state(
    *,
    repository_id: str = "react/react",
    index_version: str = DEFAULT_INDEX_VERSION,
    synced_at: str = DEFAULT_SYNCED_AT,
) -> SyncState:
    """Return an initial status state with all Phase5 artifact streams visible."""

    watermarks = tuple(
        SyncWatermark(artifact_kind=kind, updated_at=synced_at)
        for kind in ArtifactSyncKind
    )
    return SyncState(
        repository_id=repository_id,
        index_version=index_version,
        synced_at=synced_at,
        watermarks=watermarks,
    )


def build_scheduler_config(
    *,
    enabled: bool = False,
    interval_minutes: int = 60,
) -> SchedulerConfig:
    """Describe scheduler settings without registering a scheduler job."""

    return SchedulerConfig(
        enabled=enabled,
        interval_minutes=interval_minutes,
        command="uv --system-certs run python -m git_archaeologist.ops.phase5_sync --plan",
        mutates_external_scheduler=False,
    )


def build_phase5_sync_status_report(
    state: SyncState,
    *,
    scheduler: SchedulerConfig | None = None,
) -> Phase5SyncStatusReport:
    """Build a JSON-friendly status report from a published sync state."""

    return Phase5SyncStatusReport(
        status="phase5_sync_status_ready",
        repository_id=state.repository_id,
        index_version=state.index_version,
        synced_at=state.synced_at,
        watermarks=tuple(_watermark_to_dict(mark) for mark in state.watermarks),
        tombstones=state.tombstones,
        scheduler=scheduler or build_scheduler_config(),
        manual_sync_command="uv --system-certs run python -m git_archaeologist.ops.phase5_sync --plan",
    )


def build_phase5_manual_sync_plan_report(
    state: SyncState,
    observed_updates: tuple[ArtifactUpdate, ...],
    *,
    scheduler: SchedulerConfig | None = None,
) -> Phase5ManualSyncPlanReport:
    """Plan selected artifacts for a manual sync without collecting anything."""

    plan = plan_incremental_sync(state, observed_updates)
    return _manual_plan_report(
        state,
        observed_updates=observed_updates,
        plan=plan,
        scheduler=scheduler or build_scheduler_config(),
    )


def load_sync_state(path: Path) -> SyncState:
    """Load a sync state JSON file used by --status and --plan."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return SyncState(
        repository_id=str(payload["repository_id"]),
        index_version=str(payload["index_version"]),
        synced_at=str(payload["synced_at"]),
        watermarks=tuple(
            SyncWatermark(
                artifact_kind=ArtifactSyncKind(str(item["artifact_kind"])),
                updated_at=str(item["updated_at"]),
                cursor=str(item["cursor"]) if item.get("cursor") is not None else None,
                head_sha=str(item["head_sha"]) if item.get("head_sha") is not None else None,
            )
            for item in payload.get("watermarks", [])
        ),
        tombstones=tuple(str(item) for item in payload.get("tombstones", [])),
    )


def load_observed_updates(path: Path) -> tuple[ArtifactUpdate, ...]:
    """Load observed artifact updates from a JSON file."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("observed updates file must contain a JSON list")
    return tuple(_artifact_update_from_dict(item) for item in payload)


def report_to_json(report: Phase5SyncStatusReport | Phase5ManualSyncPlanReport) -> str:
    """Serialize a status or plan report."""

    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def _manual_plan_report(
    state: SyncState,
    *,
    observed_updates: tuple[ArtifactUpdate, ...],
    plan: IncrementalSyncPlan,
    scheduler: SchedulerConfig,
) -> Phase5ManualSyncPlanReport:
    return Phase5ManualSyncPlanReport(
        status="phase5_manual_sync_plan_ready",
        repository_id=state.repository_id,
        index_version=state.index_version,
        observed_update_count=len(observed_updates),
        selected_updates=tuple(_artifact_update_to_dict(update) for update in plan.updates),
        skipped_artifact_ids=plan.skipped_artifact_ids,
        scheduler=scheduler,
        external_collection_executed=False,
    )


def _watermark_to_dict(mark: SyncWatermark) -> dict[str, object]:
    return {
        "artifact_kind": mark.artifact_kind.value,
        "updated_at": mark.updated_at,
        "cursor": mark.cursor,
        "head_sha": mark.head_sha,
    }


def _artifact_update_to_dict(update: ArtifactUpdate) -> dict[str, object]:
    return {
        "artifact_kind": update.artifact_kind.value,
        "artifact_id": update.artifact_id,
        "updated_at": update.updated_at,
        "cursor": update.cursor,
        "head_sha": update.head_sha,
        "deleted": update.deleted,
    }


def _artifact_update_from_dict(item: Any) -> ArtifactUpdate:
    if not isinstance(item, dict):
        raise ValueError("each observed update must be an object")
    return ArtifactUpdate(
        artifact_kind=ArtifactSyncKind(str(item["artifact_kind"])),
        artifact_id=str(item["artifact_id"]),
        updated_at=str(item["updated_at"]),
        cursor=str(item["cursor"]) if item.get("cursor") is not None else None,
        head_sha=str(item["head_sha"]) if item.get("head_sha") is not None else None,
        deleted=bool(item.get("deleted", False)),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="print current sync status")
    mode.add_argument("--plan", action="store_true", help="print a manual sync plan")
    parser.add_argument("--repository-id", default="react/react")
    parser.add_argument("--state-file", type=Path, default=None)
    parser.add_argument("--observed-updates", type=Path, default=None)
    parser.add_argument("--enable-scheduler", action="store_true")
    parser.add_argument("--scheduler-interval-minutes", type=int, default=60)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    state = (
        load_sync_state(args.state_file)
        if args.state_file is not None
        else build_default_sync_state(
            repository_id=args.repository_id,
            synced_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    scheduler = build_scheduler_config(
        enabled=args.enable_scheduler,
        interval_minutes=args.scheduler_interval_minutes,
    )
    if args.plan:
        updates = load_observed_updates(args.observed_updates) if args.observed_updates else ()
        report = build_phase5_manual_sync_plan_report(
            state,
            updates,
            scheduler=scheduler,
        )
    else:
        report = build_phase5_sync_status_report(state, scheduler=scheduler)
    print(report_to_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
