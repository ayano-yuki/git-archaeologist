"""Phase 5 operation plans."""

from __future__ import annotations

from git_archaeologist.evaluation.phase5_regression import PHASE5_REGRESSION_SUITE_ID
from git_archaeologist.ops.operations import RegressionSuitePlan


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
