"""Phase5 local operations, sync, data protection, and QA planning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path


class OperationStatus(StrEnum):
    """Local operation readiness state."""

    READY = "ready"
    BLOCKED = "blocked"
    PENDING = "pending"


@dataclass(frozen=True)
class OperationStep:
    """One reproducible local operation step."""

    step_id: str
    command: str
    status: OperationStatus
    reason: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class Phase5OperationsPlan:
    """End-user runnable plan for local setup, sync, training, and QA."""

    repository_id: str
    model_id: str
    setup_steps: tuple[OperationStep, ...]
    sync_steps: tuple[OperationStep, ...]
    training_steps: tuple[OperationStep, ...]
    qa_steps: tuple[OperationStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "setup_steps", tuple(self.setup_steps))
        object.__setattr__(self, "sync_steps", tuple(self.sync_steps))
        object.__setattr__(self, "training_steps", tuple(self.training_steps))
        object.__setattr__(self, "qa_steps", tuple(self.qa_steps))
        if not self.repository_id:
            raise ValueError("repository_id must be non-empty")
        if not self.model_id:
            raise ValueError("model_id must be non-empty")

    @property
    def all_steps(self) -> tuple[OperationStep, ...]:
        return self.setup_steps + self.sync_steps + self.training_steps + self.qa_steps

    @property
    def status(self) -> OperationStatus:
        if any(step.status is OperationStatus.BLOCKED for step in self.all_steps):
            return OperationStatus.BLOCKED
        if any(step.status is OperationStatus.PENDING for step in self.all_steps):
            return OperationStatus.PENDING
        return OperationStatus.READY

    def to_dict(self) -> dict[str, object]:
        return {
            "repository_id": self.repository_id,
            "model_id": self.model_id,
            "status": self.status.value,
            "setup_steps": [step.to_dict() for step in self.setup_steps],
            "sync_steps": [step.to_dict() for step in self.sync_steps],
            "training_steps": [step.to_dict() for step in self.training_steps],
            "qa_steps": [step.to_dict() for step in self.qa_steps],
        }


@dataclass(frozen=True)
class ProtectedDataInventory:
    """List local data roots and explicit deletion boundaries."""

    repository_id: str
    data_roots: tuple[str, ...]
    deletable_patterns: tuple[str, ...]
    protected_patterns: tuple[str, ...]
    redaction_required: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_roots", tuple(self.data_roots))
        object.__setattr__(self, "deletable_patterns", tuple(self.deletable_patterns))
        object.__setattr__(self, "protected_patterns", tuple(self.protected_patterns))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RegressionSuitePlan:
    """Unified regression suite across target, search, answer, lineage, incidents, and leakage."""

    suite_id: str
    commands: tuple[str, ...]
    required_reports: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "commands", tuple(self.commands))
        object.__setattr__(self, "required_reports", tuple(self.required_reports))
        if not self.suite_id:
            raise ValueError("suite_id must be non-empty")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_phase5_operations_plan(
    *,
    repository_id: str = "react/react",
    model_id: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
    include_training_execute: bool = False,
) -> Phase5OperationsPlan:
    """Build the reproducible command plan needed to operate Phase5 locally."""

    training_execute_status = OperationStatus.READY if include_training_execute else OperationStatus.PENDING
    training_execute_reason = (
        "User requested production training execution."
        if include_training_execute
        else "Heavy QLoRA execution is intentionally explicit; run after readiness passes."
    )
    return Phase5OperationsPlan(
        repository_id=repository_id,
        model_id=model_id,
        setup_steps=(
            OperationStep("runtime-smoke", "uv --system-certs run python -m git_archaeologist.evaluation.system_smoke", OperationStatus.READY, "Checks local runtime profile and baseline data."),
            OperationStep("training-deps-smoke", "uv --system-certs run --extra training python -m git_archaeologist.evaluation.system_smoke --require-training-dependencies", OperationStatus.READY, "Verifies optional training dependencies before model loading."),
        ),
        sync_steps=(
            OperationStep("manual-incremental-sync", "uv --system-certs run python -m git_archaeologist.ops.phase2_smoke", OperationStatus.READY, "Exercises incremental sync and index generation safeguards."),
            OperationStep("question-time-current-pr", "uv --system-certs run python -m git_archaeologist.demo_chat", OperationStatus.READY, "Verifies current PR context can be attached to a chat turn."),
        ),
        training_steps=(
            OperationStep("production-training-readiness", "uv --system-certs run python -m git_archaeologist.evaluation.production_training", OperationStatus.READY, "Validates production raw-data coverage, SFT plan, and dataset without loading the model."),
            OperationStep("production-training-execute", "uv --system-certs run --extra training python -m git_archaeologist.evaluation.train_sft --execute", training_execute_status, training_execute_reason),
            OperationStep("post-sft-evaluation", "uv --system-certs run python -m git_archaeologist.evaluation.post_sft_evaluation", OperationStatus.READY, "Writes the post-FT comparison and leakage report."),
        ),
        qa_steps=(
            OperationStep("unit-regression", "uv --system-certs run python -m unittest discover tests", OperationStatus.READY, "Runs all feature-family regression tests."),
            OperationStep("performance-profile", "uv --system-certs run python -m git_archaeologist.evaluation.runtime_profile", OperationStatus.READY, "Records local performance and resource constraints."),
        ),
    )


def build_protected_data_inventory(
    *,
    repository_id: str = "react/react",
    data_root: Path = Path("data"),
) -> ProtectedDataInventory:
    """Describe what local data exists and which deletion patterns are allowed."""

    roots = tuple(str(path) for path in sorted(data_root.glob("*")) if path.is_dir())
    return ProtectedDataInventory(
        repository_id=repository_id,
        data_roots=roots,
        deletable_patterns=(
            "data/local-runtime/raw/<owner>/<repo>/<artifact-kind>/*.json",
            "data/local-runtime/runs/<run-id>/*",
            "data/<model-name>/runs/<run-id>/*",
        ),
        protected_patterns=(
            "authorization_header",
            "raw_token",
            "secret_value",
            "private_key",
            "unredacted_private_repository_artifact",
        ),
        redaction_required=True,
    )


def build_regression_suite_plan() -> RegressionSuitePlan:
    """Return the Phase5 regression commands and expected reports."""

    return RegressionSuitePlan(
        suite_id="phase5-regression-suite-v1",
        commands=(
            "uv --system-certs run python -m unittest discover tests",
            "uv --system-certs run python -m git_archaeologist.evaluation.post_sft_evaluation",
            "uv --system-certs run python -m git_archaeologist.evaluation.runtime_profile",
        ),
        required_reports=(
            "data/Qwen--Qwen2.5-Coder-7B-Instruct/eval/post-sft/answer-discipline-post-sft-report.json",
            "data/<model-name>/runs/runtime-profile/runtime-profile.json",
        ),
    )
