"""Phase 5 chat end-to-end performance measurement.

The runner measures deterministic chat backends by default. It records stage
latency and best-effort local resources without training models or invoking a
real heavy inference runtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import argparse
import ctypes
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Protocol

from git_archaeologist.evaluation.runtime_profile import (
    MVP_RUNTIME_PROFILE_ID,
    RUNTIME_PROFILE_VERSION,
    model_name_to_data_dir_name,
)
from git_archaeologist.ops.query_trace import (
    QueryTrace,
    ResourceReading,
    StagePerformanceMeasurement,
    build_stage_performance_measurement,
    start_query_trace,
)


PHASE5_PERFORMANCE_VERSION = "phase5-chat-performance-v1"
DEFAULT_PERFORMANCE_STAGES = (
    "target_resolution",
    "search",
    "rerank",
    "answer_generation",
    "citation_verification",
)


class Phase5Stage(StrEnum):
    """Chat E2E stages measured for Phase 5."""

    TARGET_RESOLUTION = "target_resolution"
    SEARCH = "search"
    RERANK = "rerank"
    ANSWER_GENERATION = "answer_generation"
    CITATION_VERIFICATION = "citation_verification"


@dataclass(frozen=True)
class ChatPerformanceCase:
    """One evaluation chat case for deterministic performance measurement."""

    case_id: str
    raw_input: str
    expected_status: str = "answered"

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id must be non-empty")
        if not self.raw_input:
            raise ValueError("raw_input must be non-empty")
        if not self.expected_status:
            raise ValueError("expected_status must be non-empty")


@dataclass(frozen=True)
class StageRunResult:
    """Backend result for one stage."""

    status: str = "ok"
    payload: dict[str, object] | None = None


class ChatPerformanceBackend(Protocol):
    """Deterministic backend boundary for stage-by-stage chat measurement."""

    def run_stage(self, case: ChatPerformanceCase, stage: Phase5Stage) -> StageRunResult:
        """Run one lightweight stage and return its trace payload."""


class ResourceSampler(Protocol):
    """Best-effort local resource sampler."""

    def sample(self) -> ResourceReading:
        """Return a point-in-time reading. Unknown fields must be None."""


@dataclass(frozen=True)
class StagePerformanceRecord:
    """Measured performance for one case and one stage."""

    case_id: str
    stage: str
    status: str
    latency_ms: float
    cpu_seconds_delta: float | None
    ram_bytes: int | None
    gpu_utilization_percent: float | None
    vram_bytes: int | None
    resource_status: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class StagePerformanceSummary:
    """Aggregate performance for one chat stage."""

    stage: str
    sample_count: int
    representative_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float
    resource_status: str


@dataclass(frozen=True)
class BottleneckSummary:
    """Highest latency stage in the measured report."""

    stage: str
    reason: str
    p95_latency_ms: float


@dataclass(frozen=True)
class Phase5PerformanceReport:
    """Serializable report for Phase 5 chat E2E performance."""

    schema_version: str
    runtime_profile_version: str
    profile_id: str
    measured_at: str
    case_count: int
    stages: tuple[str, ...]
    stage_records: tuple[StagePerformanceRecord, ...]
    stage_summaries: tuple[StagePerformanceSummary, ...]
    bottleneck: BottleneckSummary
    traces: tuple[QueryTrace, ...]
    notes: tuple[str, ...] = ()


class DeterministicChatPerformanceBackend:
    """Mock backend that exercises the pipeline without heavy model execution."""

    def run_stage(self, case: ChatPerformanceCase, stage: Phase5Stage) -> StageRunResult:
        payload: dict[str, object] = {
            "case_id": case.case_id,
            "backend": "deterministic",
            "external_model_invoked": False,
        }
        if stage is Phase5Stage.TARGET_RESOLUTION:
            payload["candidate_count"] = 1
            payload["selected_target_id"] = f"{case.case_id}-target"
        elif stage is Phase5Stage.SEARCH:
            payload["candidate_count"] = 3
            payload["query_source"] = "mock_index"
        elif stage is Phase5Stage.RERANK:
            payload["rerank_order"] = ("source-1", "source-2", "source-3")
        elif stage is Phase5Stage.ANSWER_GENERATION:
            payload["model_version"] = "deterministic-answer-backend"
            payload["verdict"] = case.expected_status
        elif stage is Phase5Stage.CITATION_VERIFICATION:
            payload["is_supported"] = True
        return StageRunResult(status="ok", payload=payload)


class DefaultProcessResourceSampler:
    """Portable best-effort resource sampler with safe unknown fallbacks."""

    def __init__(self, *, include_gpu: bool = True) -> None:
        self._include_gpu = include_gpu

    def sample(self) -> ResourceReading:
        notes: list[str] = []
        ram_bytes, ram_note = _detect_process_ram_bytes()
        if ram_note:
            notes.append(ram_note)
        gpu_percent = None
        vram_bytes = None
        if self._include_gpu:
            gpu_percent, vram_bytes, gpu_note = _detect_nvidia_usage()
            if gpu_note:
                notes.append(gpu_note)
        return ResourceReading(
            cpu_seconds=time.process_time(),
            ram_bytes=ram_bytes,
            gpu_utilization_percent=gpu_percent,
            vram_bytes=vram_bytes,
            notes=tuple(notes),
        )


class UnknownResourceSampler:
    """Sampler used by tests and unsupported environments."""

    def sample(self) -> ResourceReading:
        return ResourceReading(notes=("resource counters unavailable",))


def measure_chat_case(
    case: ChatPerformanceCase,
    *,
    backend: ChatPerformanceBackend,
    index_version: str,
    model_version: str,
    resource_sampler: ResourceSampler | None = None,
    clock: Any = time.perf_counter,
    stages: tuple[Phase5Stage, ...] = tuple(Phase5Stage),
) -> tuple[QueryTrace, tuple[StagePerformanceRecord, ...]]:
    """Measure one chat case stage-by-stage and return its QueryTrace."""

    trace = start_query_trace(
        case.raw_input,
        index_version=index_version,
        model_version=model_version,
        query_id=case.case_id,
    )
    sampler = resource_sampler or DefaultProcessResourceSampler()
    records: list[StagePerformanceRecord] = []

    for stage in stages:
        started_at = float(clock())
        start_resources = sampler.sample()
        result = backend.run_stage(case, stage)
        end_resources = sampler.sample()
        finished_at = float(clock())
        measurement = build_stage_performance_measurement(
            stage=stage.value,
            started_at_seconds=started_at,
            finished_at_seconds=finished_at,
            start_resources=start_resources,
            end_resources=end_resources,
        )
        trace = trace.add_performance_step(
            stage.value,
            result.status,
            result.payload or {},
            measurement,
        )
        records.append(_record_from_measurement(case.case_id, result.status, measurement))

    return trace.complete(case.expected_status), tuple(records)


def build_phase5_performance_report(
    cases: tuple[ChatPerformanceCase, ...],
    *,
    backend: ChatPerformanceBackend | None = None,
    index_version: str = "deterministic-index",
    model_version: str = "deterministic-model",
    resource_sampler: ResourceSampler | None = None,
    clock: Any = time.perf_counter,
    measured_at: datetime | None = None,
) -> Phase5PerformanceReport:
    """Run deterministic chat performance cases and summarize bottlenecks."""

    if not cases:
        raise ValueError("cases must not be empty")
    timestamp = measured_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("measured_at must include a timezone")

    active_backend = backend or DeterministicChatPerformanceBackend()
    traces: list[QueryTrace] = []
    records: list[StagePerformanceRecord] = []
    for case in cases:
        trace, case_records = measure_chat_case(
            case,
            backend=active_backend,
            index_version=index_version,
            model_version=model_version,
            resource_sampler=resource_sampler,
            clock=clock,
        )
        traces.append(trace)
        records.extend(case_records)

    summaries = summarize_stage_records(tuple(records), DEFAULT_PERFORMANCE_STAGES)
    bottleneck = explain_bottleneck(summaries)
    return Phase5PerformanceReport(
        schema_version=PHASE5_PERFORMANCE_VERSION,
        runtime_profile_version=RUNTIME_PROFILE_VERSION,
        profile_id=MVP_RUNTIME_PROFILE_ID,
        measured_at=timestamp.astimezone(timezone.utc).isoformat(),
        case_count=len(cases),
        stages=DEFAULT_PERFORMANCE_STAGES,
        stage_records=tuple(records),
        stage_summaries=summaries,
        bottleneck=bottleneck,
        traces=tuple(traces),
        notes=(
            "Measurements may vary by local machine and should be compared within the same runtime profile.",
            "Default backend is deterministic and does not train models or invoke real heavy inference.",
        ),
    )


def summarize_stage_records(
    records: tuple[StagePerformanceRecord, ...],
    stages: tuple[str, ...],
) -> tuple[StagePerformanceSummary, ...]:
    """Build p95 and representative latency summaries for each stage."""

    summaries: list[StagePerformanceSummary] = []
    for stage in stages:
        stage_records = [record for record in records if record.stage == stage]
        if not stage_records:
            continue
        latencies = tuple(record.latency_ms for record in stage_records)
        summaries.append(
            StagePerformanceSummary(
                stage=stage,
                sample_count=len(stage_records),
                representative_latency_ms=_percentile(latencies, 50),
                p95_latency_ms=_percentile(latencies, 95),
                max_latency_ms=max(latencies),
                resource_status=_combine_resource_status(
                    tuple(record.resource_status for record in stage_records)
                ),
            )
        )
    return tuple(summaries)


def explain_bottleneck(
    summaries: tuple[StagePerformanceSummary, ...],
) -> BottleneckSummary:
    """Return the stage with the largest p95 latency."""

    if not summaries:
        raise ValueError("summaries must not be empty")
    slowest = max(summaries, key=lambda summary: summary.p95_latency_ms)
    return BottleneckSummary(
        stage=slowest.stage,
        p95_latency_ms=slowest.p95_latency_ms,
        reason=(
            f"{slowest.stage} has the highest p95 latency "
            f"({slowest.p95_latency_ms:.2f} ms) across measured chat cases."
        ),
    )


def phase5_performance_report_to_dict(
    report: Phase5PerformanceReport,
) -> dict[str, object]:
    """Return a JSON-friendly Phase 5 performance report."""

    payload = asdict(report)
    payload["traces"] = [trace.to_dict() for trace in report.traces]
    return payload


def phase5_performance_report_to_json(report: Phase5PerformanceReport) -> str:
    """Return formatted JSON for a Phase 5 performance report."""

    return json.dumps(
        phase5_performance_report_to_dict(report),
        ensure_ascii=False,
        indent=2,
    )


def phase5_performance_summary_to_markdown(report: Phase5PerformanceReport) -> str:
    """Return a human-readable performance summary."""

    lines = [
        "# Phase 5 Chat E2E Performance",
        "",
        f"- Schema: `{report.schema_version}`",
        f"- Runtime profile: `{report.profile_id}` / `{report.runtime_profile_version}`",
        f"- Measured at: `{report.measured_at}`",
        f"- Cases: `{report.case_count}`",
        f"- Bottleneck: `{report.bottleneck.stage}` ({report.bottleneck.p95_latency_ms:.2f} ms p95)",
        "",
        "| Stage | Samples | Representative ms | p95 ms | Max ms | Resource status |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for summary in report.stage_summaries:
        lines.append(
            "| "
            f"{summary.stage} | "
            f"{summary.sample_count} | "
            f"{summary.representative_latency_ms:.2f} | "
            f"{summary.p95_latency_ms:.2f} | "
            f"{summary.max_latency_ms:.2f} | "
            f"{summary.resource_status} |"
        )
    lines.extend(
        [
            "",
            "## Bottleneck",
            "",
            report.bottleneck.reason,
            "",
            "## Notes",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines) + "\n"


def write_phase5_performance_report(
    report: Phase5PerformanceReport,
    *,
    output_dir: str | Path,
    json_filename: str = "phase5-performance.json",
    markdown_filename: str = "phase5-performance.md",
) -> tuple[Path, Path]:
    """Write report JSON and summary markdown under output_dir."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / json_filename
    markdown_path = root / markdown_filename
    json_path.write_text(phase5_performance_report_to_json(report) + "\n", encoding="utf-8")
    markdown_path.write_text(
        phase5_performance_summary_to_markdown(report),
        encoding="utf-8",
    )
    return json_path, markdown_path


def default_phase5_output_dir(
    *,
    data_root: str | Path = "data",
    model_name: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
) -> Path:
    """Return the conventional model run directory for Phase 5 performance."""

    model_dir = model_name_to_data_dir_name(model_name)
    return Path(data_root) / model_dir / "runs" / "phase5-performance"


def _record_from_measurement(
    case_id: str,
    status: str,
    measurement: StagePerformanceMeasurement,
) -> StagePerformanceRecord:
    return StagePerformanceRecord(
        case_id=case_id,
        stage=measurement.stage,
        status=status,
        latency_ms=measurement.latency_ms,
        cpu_seconds_delta=measurement.cpu_seconds_delta,
        ram_bytes=measurement.ram_bytes,
        gpu_utilization_percent=measurement.gpu_utilization_percent,
        vram_bytes=measurement.vram_bytes,
        resource_status=measurement.resource_status,
        notes=measurement.notes,
    )


def _percentile(values: tuple[float, ...], percentile: int) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if percentile <= 0 or percentile > 100:
        raise ValueError("percentile must be in the range 1..100")
    ordered = sorted(values)
    index = math.ceil((percentile / 100) * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _combine_resource_status(statuses: tuple[str, ...]) -> str:
    if not statuses:
        return "unknown"
    if all(status == "unknown" for status in statuses):
        return "unknown"
    if all(status == "measured" for status in statuses):
        return "measured"
    return "partial"


def _detect_process_ram_bytes() -> tuple[int | None, str | None]:
    if sys.platform == "win32":
        return _detect_windows_process_ram_bytes()

    try:
        import resource
    except ImportError:
        return None, "process RAM detection is unavailable on this platform"

    try:
        max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (OSError, ValueError):
        return None, "process RAM detection failed"
    if max_rss <= 0:
        return None, "process RAM detection returned no value"
    if sys.platform == "darwin":
        return int(max_rss), None
    return int(max_rss) * 1024, None


def _detect_windows_process_ram_bytes() -> tuple[int | None, str | None]:
    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(ProcessMemoryCounters)
    try:
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
    except AttributeError:
        return None, "Windows process RAM detection is unavailable"
    if not ok:
        return None, "GetProcessMemoryInfo failed"
    return int(counters.WorkingSetSize), None


def _detect_nvidia_usage() -> tuple[float | None, int | None, str | None]:
    if shutil.which("nvidia-smi") is None:
        return None, None, "nvidia-smi was not available; GPU resource fields are unknown"
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None, "nvidia-smi failed; GPU resource fields are unknown"
    if result.returncode != 0:
        return None, None, "nvidia-smi returned no usable GPU resource fields"
    gpu_percent_values: list[float] = []
    vram_values: list[int] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",", 1)]
        if len(parts) != 2:
            continue
        try:
            gpu_percent_values.append(float(parts[0]))
            vram_values.append(int(parts[1]) * 1024 * 1024)
        except ValueError:
            continue
    if not gpu_percent_values and not vram_values:
        return None, None, "nvidia-smi output could not be parsed"
    gpu_percent = max(gpu_percent_values) if gpu_percent_values else None
    vram_bytes = max(vram_values) if vram_values else None
    return gpu_percent, vram_bytes, None


def _build_default_cases() -> tuple[ChatPerformanceCase, ...]:
    return (
        ChatPerformanceCase(
            case_id="phase5-deterministic-case",
            raw_input=(
                "https://github.com/example/repo/pull/123 "
                "src/example.py の実装理由と変更リスクを説明して"
            ),
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(default_phase5_output_dir()),
        help="Directory for phase5-performance.json and phase5-performance.md.",
    )
    parser.add_argument(
        "--no-gpu",
        action="store_true",
        help="Skip nvidia-smi sampling and record GPU/VRAM fields as unknown.",
    )
    args = parser.parse_args(argv)

    report = build_phase5_performance_report(
        _build_default_cases(),
        resource_sampler=DefaultProcessResourceSampler(include_gpu=not args.no_gpu),
    )
    json_path, markdown_path = write_phase5_performance_report(
        report,
        output_dir=args.output_dir,
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
