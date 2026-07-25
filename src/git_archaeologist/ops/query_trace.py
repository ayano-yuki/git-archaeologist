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
