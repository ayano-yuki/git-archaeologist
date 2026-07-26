"""Runtime and model constraint profiling for the MVP.

The profiler intentionally uses only the Python standard library so that a
fresh checkout can record local constraints before model runtimes are installed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import ctypes
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any


RUNTIME_PROFILE_VERSION = "runtime-profile-v1"
MVP_RUNTIME_PROFILE_ID = "mvp-local-runtime-v1"
GIB = 1024**3
MIB = 1024**2


class ModelRole(StrEnum):
    """Model roles used by the MVP architecture."""

    EMBEDDING = "embedding"
    RERANKER = "reranker"
    ANSWER_JUDGE = "answer_judge"


@dataclass(frozen=True)
class GpuDevice:
    """Detected GPU device and memory information."""

    name: str
    total_memory_bytes: int | None


@dataclass(frozen=True)
class HardwareProfile:
    """Local machine constraints relevant to model selection."""

    operating_system: str
    machine: str
    processor: str
    python_version: str
    logical_cpu_count: int | None
    total_ram_bytes: int | None
    disk_path: str
    disk_total_bytes: int
    disk_free_bytes: int
    gpu_devices: tuple[GpuDevice, ...]
    notes: tuple[str, ...]

    @property
    def largest_gpu_memory_bytes(self) -> int | None:
        memories = [
            device.total_memory_bytes
            for device in self.gpu_devices
            if device.total_memory_bytes is not None
        ]
        return max(memories) if memories else None


@dataclass(frozen=True)
class ModelConstraint:
    """Chosen MVP model and the constraint envelope it must fit."""

    role: ModelRole
    model_id: str
    purpose: str
    quantization: str
    max_context_tokens: int
    batch_size: int
    minimum_ram_bytes: int
    recommended_vram_bytes: int | None
    benchmark_workload: str
    acceptance_target: str


@dataclass(frozen=True)
class ConstraintCheck:
    """Whether the current hardware can run a selected model candidate."""

    role: ModelRole
    model_id: str
    status: str
    reason: str


@dataclass(frozen=True)
class RuntimeBenchmarkResult:
    """Measured performance for one selected model role."""

    role: ModelRole
    model_id: str
    workload: str
    status: str
    throughput_per_second: float | None
    p95_latency_seconds: float | None
    peak_ram_bytes: int | None
    peak_vram_bytes: int | None
    notes: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeBenchmarkReport:
    """Benchmark results tied to a runtime profile."""

    schema_version: str
    profile_id: str
    measured_at: str
    results: tuple[RuntimeBenchmarkResult, ...]


@dataclass(frozen=True)
class RuntimeProfileErrorReport:
    """Human escalation payload for runtime profiling failures."""

    operation: str
    error_type: str
    error_message: str
    model_id: str | None
    profile_id: str
    retry_count: int
    suppressed_fields: tuple[str, ...]


@dataclass(frozen=True)
class IndexOptimizationSettings:
    """Index-side knobs compared during Phase 5 optimization."""

    embedding_cache: str
    context_compression_ratio: float
    candidate_count: int
    rerank_top_k: int

    def __post_init__(self) -> None:
        if self.embedding_cache not in {"disabled", "memory", "disk"}:
            raise ValueError("embedding_cache must be disabled, memory, or disk")
        if not 0 < self.context_compression_ratio <= 1:
            raise ValueError("context_compression_ratio must be in the range (0, 1]")
        if self.candidate_count <= 0:
            raise ValueError("candidate_count must be positive")
        if self.rerank_top_k <= 0:
            raise ValueError("rerank_top_k must be positive")
        if self.rerank_top_k > self.candidate_count:
            raise ValueError("rerank_top_k must be <= candidate_count")


@dataclass(frozen=True)
class RuntimeOptimizationProfile:
    """Model and index profile considered by the optimization report."""

    profile_id: str
    model_id: str
    quantization: str
    max_context_tokens: int
    batch_size: int
    index: IndexOptimizationSettings
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("profile_id must be non-empty")
        if not self.model_id:
            raise ValueError("model_id must be non-empty")
        if not self.quantization:
            raise ValueError("quantization must be non-empty")
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")


@dataclass(frozen=True)
class RuntimeProfile:
    """Complete runtime profile payload that can be serialized to JSON."""

    schema_version: str
    profile_id: str
    captured_at: str
    hardware: HardwareProfile
    selected_models: tuple[ModelConstraint, ...]
    constraint_checks: tuple[ConstraintCheck, ...]
    measurement_policy: str


def collect_hardware_profile(disk_path: str | Path = ".") -> HardwareProfile:
    """Collect local CPU, RAM, disk, and optional NVIDIA GPU information."""

    resolved_disk_path = Path(disk_path).resolve()
    disk_usage = shutil.disk_usage(resolved_disk_path)
    total_ram_bytes, ram_note = _detect_total_ram_bytes()
    gpu_devices, gpu_note = _detect_nvidia_gpus()
    notes = tuple(note for note in (ram_note, gpu_note) if note)

    return HardwareProfile(
        operating_system=platform.platform(),
        machine=platform.machine(),
        processor=platform.processor(),
        python_version=platform.python_version(),
        logical_cpu_count=os.cpu_count(),
        total_ram_bytes=total_ram_bytes,
        disk_path=str(resolved_disk_path),
        disk_total_bytes=disk_usage.total,
        disk_free_bytes=disk_usage.free,
        gpu_devices=gpu_devices,
        notes=notes,
    )


def load_mvp_model_constraints() -> tuple[ModelConstraint, ...]:
    """Return the fixed initial model envelope for MVP benchmarking."""

    return (
        ModelConstraint(
            role=ModelRole.EMBEDDING,
            model_id="BAAI/bge-m3",
            purpose="Generate multilingual Japanese, English, and code embeddings for history chunks.",
            quantization="fp16-or-int8-runtime",
            max_context_tokens=8192,
            batch_size=16,
            minimum_ram_bytes=8 * GIB,
            recommended_vram_bytes=None,
            benchmark_workload="Embed 100 representative PR, review, diff, and commit-message chunks.",
            acceptance_target="Complete the workload in <= 10 seconds after model warmup.",
        ),
        ModelConstraint(
            role=ModelRole.RERANKER,
            model_id="BAAI/bge-reranker-v2-m3",
            purpose="Rerank hybrid-search candidates by question relevance and evidence strength.",
            quantization="fp16-or-int8-runtime",
            max_context_tokens=8192,
            batch_size=8,
            minimum_ram_bytes=8 * GIB,
            recommended_vram_bytes=None,
            benchmark_workload="Rerank 50 question/evidence pairs from the frozen MVP evaluation set.",
            acceptance_target="Complete the workload in <= 5 seconds after model warmup.",
        ),
        ModelConstraint(
            role=ModelRole.ANSWER_JUDGE,
            model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
            purpose="Generate evidence-bound rationale, risk judgment, abstention, and citation-aware answers.",
            quantization="4-bit LoRA-compatible local runtime",
            max_context_tokens=32768,
            batch_size=1,
            minimum_ram_bytes=15 * GIB,
            recommended_vram_bytes=8 * GIB,
            benchmark_workload="Generate one structured answer from a 24k-token Evidence Pack plus verifier prompts.",
            acceptance_target="Reach >= 8 output tokens/second or keep p95 answer latency <= 30 seconds.",
        ),
    )


def load_default_optimization_profiles() -> tuple[RuntimeOptimizationProfile, ...]:
    """Return deterministic Phase 5 model/index profiles for comparison."""

    return (
        RuntimeOptimizationProfile(
            profile_id="baseline-qwen-4bit-full-context",
            model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
            quantization="4-bit LoRA-compatible local runtime",
            max_context_tokens=32768,
            batch_size=1,
            index=IndexOptimizationSettings(
                embedding_cache="disabled",
                context_compression_ratio=1.0,
                candidate_count=50,
                rerank_top_k=20,
            ),
            notes=("Baseline profile before Phase 5 optimization.",),
        ),
        RuntimeOptimizationProfile(
            profile_id="cache-compressed-context",
            model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
            quantization="4-bit LoRA-compatible local runtime",
            max_context_tokens=24576,
            batch_size=1,
            index=IndexOptimizationSettings(
                embedding_cache="disk",
                context_compression_ratio=0.75,
                candidate_count=40,
                rerank_top_k=16,
            ),
            notes=("Uses embedding cache and moderate context compression.",),
        ),
        RuntimeOptimizationProfile(
            profile_id="fast-small-candidate-set",
            model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
            quantization="4-bit LoRA-compatible local runtime",
            max_context_tokens=16384,
            batch_size=1,
            index=IndexOptimizationSettings(
                embedding_cache="disk",
                context_compression_ratio=0.5,
                candidate_count=20,
                rerank_top_k=8,
            ),
            notes=("Aggressive candidate reduction; must preserve quality to be used.",),
        ),
    )


def check_runtime_constraints(
    hardware: HardwareProfile,
    constraints: tuple[ModelConstraint, ...] | None = None,
) -> tuple[ConstraintCheck, ...]:
    """Check the selected MVP models against local RAM and optional VRAM."""

    checks: list[ConstraintCheck] = []
    for constraint in constraints or load_mvp_model_constraints():
        if hardware.total_ram_bytes is None:
            checks.append(
                ConstraintCheck(
                    role=constraint.role,
                    model_id=constraint.model_id,
                    status="unknown",
                    reason="Total RAM could not be detected; run the benchmark before accepting this model.",
                )
            )
            continue

        if hardware.total_ram_bytes < constraint.minimum_ram_bytes:
            checks.append(
                ConstraintCheck(
                    role=constraint.role,
                    model_id=constraint.model_id,
                    status="blocked",
                    reason=(
                        "Detected RAM is below the minimum: "
                        f"{_format_bytes(hardware.total_ram_bytes)} < "
                        f"{_format_bytes(constraint.minimum_ram_bytes)}."
                    ),
                )
            )
            continue

        largest_gpu = hardware.largest_gpu_memory_bytes
        if (
            constraint.recommended_vram_bytes is not None
            and (largest_gpu is None or largest_gpu < constraint.recommended_vram_bytes)
        ):
            checks.append(
                ConstraintCheck(
                    role=constraint.role,
                    model_id=constraint.model_id,
                    status="cpu_or_low_vram",
                    reason=(
                        "RAM is sufficient, but recommended VRAM was not detected; "
                        "use CPU or lower-throughput GPU settings and verify latency."
                    ),
                )
            )
            continue

        checks.append(
            ConstraintCheck(
                role=constraint.role,
                model_id=constraint.model_id,
                status="ready",
                reason="Detected hardware satisfies the fixed MVP constraint envelope.",
            )
        )

    return tuple(checks)


def build_runtime_profile(
    *,
    disk_path: str | Path = ".",
    captured_at: datetime | None = None,
) -> RuntimeProfile:
    """Build a serializable runtime profile for the current machine."""

    hardware = collect_hardware_profile(disk_path)
    constraints = load_mvp_model_constraints()
    timestamp = captured_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("captured_at must include a timezone")

    return RuntimeProfile(
        schema_version=RUNTIME_PROFILE_VERSION,
        profile_id=MVP_RUNTIME_PROFILE_ID,
        captured_at=timestamp.astimezone(timezone.utc).isoformat(),
        hardware=hardware,
        selected_models=constraints,
        constraint_checks=check_runtime_constraints(hardware, constraints),
        measurement_policy=(
            "Record hardware first, then benchmark the three selected model roles "
            "with the fixed workloads before changing model IDs, quantization, "
            "context length, or acceptance targets."
        ),
    )


def runtime_profile_to_dict(profile: RuntimeProfile | None = None) -> dict[str, Any]:
    """Return a JSON-friendly runtime profile dictionary."""

    return asdict(profile or build_runtime_profile())


def runtime_profile_to_json(profile: RuntimeProfile | None = None) -> str:
    """Return a formatted JSON runtime profile."""

    return json.dumps(runtime_profile_to_dict(profile), ensure_ascii=False, indent=2)


def build_pending_benchmark_report(
    *,
    measured_at: datetime | None = None,
    constraints: tuple[ModelConstraint, ...] | None = None,
) -> RuntimeBenchmarkReport:
    """Build a benchmark report scaffold before model runtimes are installed."""

    timestamp = measured_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("measured_at must include a timezone")

    return RuntimeBenchmarkReport(
        schema_version=RUNTIME_PROFILE_VERSION,
        profile_id=MVP_RUNTIME_PROFILE_ID,
        measured_at=timestamp.astimezone(timezone.utc).isoformat(),
        results=tuple(
            RuntimeBenchmarkResult(
                role=constraint.role,
                model_id=constraint.model_id,
                workload=constraint.benchmark_workload,
                status="pending",
                throughput_per_second=None,
                p95_latency_seconds=None,
                peak_ram_bytes=None,
                peak_vram_bytes=None,
                notes=("Model runtime has not been benchmarked yet.",),
            )
            for constraint in constraints or load_mvp_model_constraints()
        ),
    )


def validate_benchmark_report(
    report: RuntimeBenchmarkReport,
    constraints: tuple[ModelConstraint, ...] | None = None,
) -> tuple[str, ...]:
    """Return validation errors for a runtime benchmark report."""

    errors: list[str] = []
    if report.schema_version != RUNTIME_PROFILE_VERSION:
        errors.append(f"unsupported schema_version: {report.schema_version}")
    if report.profile_id != MVP_RUNTIME_PROFILE_ID:
        errors.append(f"unsupported profile_id: {report.profile_id}")

    expected_constraints = constraints or load_mvp_model_constraints()
    expected = {
        (constraint.role, constraint.model_id): constraint
        for constraint in expected_constraints
    }
    actual = {(result.role, result.model_id): result for result in report.results}
    missing = expected.keys() - actual.keys()
    unexpected = actual.keys() - expected.keys()
    errors.extend(
        f"missing benchmark result: {role.value} {model_id}"
        for role, model_id in sorted(missing, key=lambda item: item[0].value)
    )
    errors.extend(
        f"unexpected benchmark result: {role.value} {model_id}"
        for role, model_id in sorted(unexpected, key=lambda item: item[0].value)
    )

    for result in report.results:
        if result.status not in {"pending", "passed", "failed", "skipped"}:
            errors.append(
                f"{result.role.value} status must be pending, passed, failed, or skipped"
            )
        if result.status in {"passed", "failed"}:
            if result.throughput_per_second is None and result.p95_latency_seconds is None:
                errors.append(
                    f"{result.role.value} measured result must include throughput or p95 latency"
                )
            if result.peak_ram_bytes is None:
                errors.append(f"{result.role.value} measured result must include peak RAM")
        if (
            result.throughput_per_second is not None
            and result.throughput_per_second <= 0
        ):
            errors.append(f"{result.role.value} throughput must be positive")
        if result.p95_latency_seconds is not None and result.p95_latency_seconds <= 0:
            errors.append(f"{result.role.value} p95 latency must be positive")
        if result.peak_ram_bytes is not None and result.peak_ram_bytes <= 0:
            errors.append(f"{result.role.value} peak RAM must be positive")
        if result.peak_vram_bytes is not None and result.peak_vram_bytes < 0:
            errors.append(f"{result.role.value} peak VRAM must not be negative")

    return tuple(errors)


def benchmark_report_to_dict(report: RuntimeBenchmarkReport) -> dict[str, Any]:
    """Return a JSON-friendly benchmark report dictionary."""

    return asdict(report)


def benchmark_report_to_json(report: RuntimeBenchmarkReport) -> str:
    """Return a formatted JSON benchmark report."""

    return json.dumps(benchmark_report_to_dict(report), ensure_ascii=False, indent=2)


def write_runtime_profile(
    profile: RuntimeProfile,
    *,
    model_name: str,
    data_root: str | Path = "data",
    filename: str = "runtime-profile.json",
) -> Path:
    """Write a runtime profile under data/<model-name>/runs/runtime-profile/."""

    model_dir = model_name_to_data_dir_name(model_name)
    output_path = Path(data_root) / model_dir / "runs" / "runtime-profile" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        runtime_profile_to_json(profile) + "\n",
        encoding="utf-8",
    )
    return output_path


def write_benchmark_report(
    report: RuntimeBenchmarkReport,
    *,
    model_name: str,
    data_root: str | Path = "data",
    filename: str = "benchmark-report.json",
) -> Path:
    """Write a benchmark report under data/<model-name>/runs/runtime-profile/."""

    model_dir = model_name_to_data_dir_name(model_name)
    output_path = Path(data_root) / model_dir / "runs" / "runtime-profile" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        benchmark_report_to_json(report) + "\n",
        encoding="utf-8",
    )
    return output_path


def model_name_to_data_dir_name(model_name: str) -> str:
    """Return the data directory name for a model ID."""

    normalized = model_name.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("model_name must not be empty")
    return normalized.replace("/", "--")


def build_runtime_profile_error_report(
    *,
    operation: str,
    error_type: str,
    error_message: str,
    model_id: str | None = None,
    retry_count: int = 0,
) -> RuntimeProfileErrorReport:
    """Build the safe human-facing payload for profiling failures."""

    if not operation:
        raise ValueError("operation must not be empty")
    if not error_type:
        raise ValueError("error_type must not be empty")
    if not error_message:
        raise ValueError("error_message must not be empty")
    if retry_count < 0:
        raise ValueError("retry_count must not be negative")

    return RuntimeProfileErrorReport(
        operation=operation,
        error_type=error_type,
        error_message=error_message,
        model_id=model_id,
        profile_id=MVP_RUNTIME_PROFILE_ID,
        retry_count=retry_count,
        suppressed_fields=(
            "authorization_header",
            "raw_token",
            "secret_value",
            "private_key",
        ),
    )


def runtime_profile_error_report_to_dict(
    report: RuntimeProfileErrorReport,
) -> dict[str, Any]:
    """Return a JSON-friendly runtime profiling error report."""

    return asdict(report)


def _detect_total_ram_bytes() -> tuple[int | None, str | None]:
    if os.name == "nt":
        return _detect_windows_ram_bytes()

    if hasattr(os, "sysconf"):
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            physical_pages = os.sysconf("SC_PHYS_PAGES")
        except (OSError, ValueError):
            return None, "Total RAM could not be detected with os.sysconf."
        if isinstance(page_size, int) and isinstance(physical_pages, int):
            return page_size * physical_pages, None

    return None, "Total RAM detection is unsupported on this platform."


def _detect_windows_ram_bytes() -> tuple[int | None, str | None]:
    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(MemoryStatusEx)
    try:
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    except AttributeError:
        return None, "Windows RAM detection is unavailable in this Python runtime."
    if not ok:
        return None, "GlobalMemoryStatusEx failed while detecting total RAM."
    return int(status.ullTotalPhys), None


def _detect_nvidia_gpus() -> tuple[tuple[GpuDevice, ...], str | None]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return (), "nvidia-smi was not available; GPU memory was not recorded."

    if result.returncode != 0:
        return (), "nvidia-smi did not return GPU information."

    devices = _parse_nvidia_smi_csv(result.stdout)
    if not devices:
        return (), "nvidia-smi returned no GPU devices."
    return devices, None


def _parse_nvidia_smi_csv(output: str) -> tuple[GpuDevice, ...]:
    devices: list[GpuDevice] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",", 1)]
        name = parts[0]
        memory_bytes = None
        if len(parts) == 2:
            try:
                memory_bytes = int(parts[1]) * MIB
            except ValueError:
                memory_bytes = None
        devices.append(GpuDevice(name=name, total_memory_bytes=memory_bytes))
    return tuple(devices)


def _format_bytes(value: int) -> str:
    if value >= GIB:
        return f"{value / GIB:.1f} GiB"
    if value >= MIB:
        return f"{value / MIB:.1f} MiB"
    return f"{value} bytes"


if __name__ == "__main__":
    print(runtime_profile_to_json())
