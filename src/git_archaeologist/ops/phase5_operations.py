"""Phase 5 local operation command plans."""

from __future__ import annotations

from dataclasses import dataclass

from git_archaeologist.evaluation.phase5_regression import PHASE5_REGRESSION_SUITE_ID
from git_archaeologist.ops.operations import (
    LocalOperationsPlan,
    RegressionSuitePlan,
    build_local_operations_plan,
)


@dataclass(frozen=True)
class Phase5OperationsReport:
    """Operator-facing Phase 5 command overview."""

    plan: LocalOperationsPlan
    data_protection_commands: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_protection_commands", tuple(self.data_protection_commands))

    def to_dict(self) -> dict[str, object]:
        return {
            "plan": self.plan.to_dict(),
            "data_protection_commands": list(self.data_protection_commands),
        }


def build_phase5_operations_report(
    *,
    repository_id: str = "react/react",
    model_id: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
) -> Phase5OperationsReport:
    """Build the Phase 5 command plan including data protection."""

    plan = build_local_operations_plan(repository_id=repository_id, model_id=model_id)
    return Phase5OperationsReport(
        plan=plan,
        data_protection_commands=(
            "uv --system-certs run python -m git_archaeologist.ops.data_protection --inventory",
            "uv --system-certs run python -m git_archaeologist.ops.data_protection --backup-plan",
            "uv --system-certs run python -m git_archaeologist.ops.data_protection --delete-plan",
        ),
    )


def build_phase5_regression_suite_plan() -> RegressionSuitePlan:
    """Return the command plan for the Phase 5 full-function regression suite."""

    return RegressionSuitePlan(
        suite_id=PHASE5_REGRESSION_SUITE_ID,
        commands=(
            (
                "uv --system-certs run python -m "
                "git_archaeologist.evaluation.phase5_regression "
                f"--suite {PHASE5_REGRESSION_SUITE_ID}"
            ),
        ),
        required_reports=(
            "data/Qwen--Qwen2.5-Coder-7B-Instruct/runs/phase5-regression/phase5-regression.json",
            "data/Qwen--Qwen2.5-Coder-7B-Instruct/runs/phase5-regression/phase5-regression.md",
        ),
    )
