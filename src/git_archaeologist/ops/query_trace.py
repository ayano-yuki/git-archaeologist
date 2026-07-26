"""Structured per-question traces for reproducing MVP answers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4


def utc_now_iso() -> str:
    """Return a stable UTC timestamp for trace and sync records."""

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class TraceStep:
    """One observable step in the chat pipeline."""

    name: str
    status: str
    payload: dict[str, object]
    occurred_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class ResourceReading:
    """Point-in-time local resource reading for a trace step."""

    cpu_seconds: float | None = None
    ram_bytes: int | None = None
    gpu_utilization_percent: float | None = None
    vram_bytes: int | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class StagePerformanceMeasurement:
    """Latency and resource usage observed for one pipeline stage."""

    stage: str
    latency_ms: float
    cpu_seconds_delta: float | None
    ram_bytes: int | None
    gpu_utilization_percent: float | None
    vram_bytes: int | None
    resource_status: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class QueryTrace:
    """Full trace for one user question."""

    query_id: str
    raw_input: str
    index_version: str
    model_version: str
    started_at: str
    completed_at: str | None = None
    result_status: str | None = None
    steps: tuple[TraceStep, ...] = ()

    def add_step(self, name: str, status: str, payload: dict[str, object]) -> "QueryTrace":
        return QueryTrace(
            query_id=self.query_id,
            raw_input=self.raw_input,
            index_version=self.index_version,
            model_version=self.model_version,
            started_at=self.started_at,
            completed_at=self.completed_at,
            result_status=self.result_status,
            steps=self.steps + (TraceStep(name=name, status=status, payload=payload),),
        )

    def add_performance_step(
        self,
        name: str,
        status: str,
        payload: dict[str, object],
        measurement: StagePerformanceMeasurement,
    ) -> "QueryTrace":
        measured_payload = dict(payload)
        measured_payload["performance"] = measurement.to_dict()
        return self.add_step(name, status, measured_payload)

    def complete(self, result_status: str) -> "QueryTrace":
        return QueryTrace(
            query_id=self.query_id,
            raw_input=self.raw_input,
            index_version=self.index_version,
            model_version=self.model_version,
            started_at=self.started_at,
            completed_at=utc_now_iso(),
            result_status=result_status,
            steps=self.steps,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class QueryTraceStore(Protocol):
    """Persistence boundary for query traces."""

    def save(self, trace: QueryTrace) -> None:
        """Persist the latest complete trace state."""


class InMemoryQueryTraceStore:
    """Small deterministic trace store for tests and local smoke checks."""

    def __init__(self) -> None:
        self._traces: dict[str, QueryTrace] = {}

    def save(self, trace: QueryTrace) -> None:
        self._traces[trace.query_id] = trace

    def get(self, query_id: str) -> QueryTrace:
        return self._traces[query_id]

    def all(self) -> tuple[QueryTrace, ...]:
        return tuple(self._traces.values())


def start_query_trace(
    raw_input: str,
    *,
    index_version: str,
    model_version: str,
    query_id: str | None = None,
) -> QueryTrace:
    """Create the root trace object for a chat request."""

    if not index_version:
        raise ValueError("index_version must be non-empty")
    if not model_version:
        raise ValueError("model_version must be non-empty")
    return QueryTrace(
        query_id=query_id or f"query-{uuid4()}",
        raw_input=raw_input,
        index_version=index_version,
        model_version=model_version,
        started_at=utc_now_iso(),
    )


def build_stage_performance_measurement(
    *,
    stage: str,
    started_at_seconds: float,
    finished_at_seconds: float,
    start_resources: ResourceReading | None = None,
    end_resources: ResourceReading | None = None,
) -> StagePerformanceMeasurement:
    """Build a trace payload for one measured chat stage."""

    if not stage:
        raise ValueError("stage must be non-empty")
    if finished_at_seconds < started_at_seconds:
        raise ValueError("finished_at_seconds must be >= started_at_seconds")

    cpu_delta = _subtract_optional(
        end_resources.cpu_seconds if end_resources else None,
        start_resources.cpu_seconds if start_resources else None,
    )
    ram_bytes = end_resources.ram_bytes if end_resources else None
    gpu_percent = end_resources.gpu_utilization_percent if end_resources else None
    vram_bytes = end_resources.vram_bytes if end_resources else None
    notes = tuple(
        dict.fromkeys(
            (start_resources.notes if start_resources else ())
            + (end_resources.notes if end_resources else ())
        )
    )

    return StagePerformanceMeasurement(
        stage=stage,
        latency_ms=(finished_at_seconds - started_at_seconds) * 1000,
        cpu_seconds_delta=cpu_delta,
        ram_bytes=ram_bytes,
        gpu_utilization_percent=gpu_percent,
        vram_bytes=vram_bytes,
        resource_status=_classify_resource_status(
            cpu_delta=cpu_delta,
            ram_bytes=ram_bytes,
            gpu_utilization_percent=gpu_percent,
            vram_bytes=vram_bytes,
        ),
        notes=notes,
    )


def _subtract_optional(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return max(0.0, value - baseline)


def _classify_resource_status(
    *,
    cpu_delta: float | None,
    ram_bytes: int | None,
    gpu_utilization_percent: float | None,
    vram_bytes: int | None,
) -> str:
    fields = (cpu_delta, ram_bytes, gpu_utilization_percent, vram_bytes)
    measured_count = sum(value is not None for value in fields)
    if measured_count == 0:
        return "unknown"
    if measured_count == len(fields):
        return "measured"
    return "partial"
