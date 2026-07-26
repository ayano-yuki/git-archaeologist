"""System smoke check for runtime, SFT data, and FT execution readiness."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Sequence

from git_archaeologist.evaluation.runtime_profile import build_runtime_profile
from git_archaeologist.evaluation.train_sft import (
    DEFAULT_PLAN_PATH,
    REQUIRED_TRAINING_MODULES,
    build_dry_run_report,
    dry_run_report_to_dict,
)
from git_archaeologist.ops.smoke import run_stability_smoke


@dataclass(frozen=True)
class SystemSmokeReport:
    """Configuration-wide smoke result before heavyweight FT execution."""

    status: str
    runtime_ready: bool
    training_plan_ready: bool
    training_execute_ready: bool
    stability_smoke_ready: bool
    missing_optional_dependencies: tuple[str, ...]
    errors: tuple[str, ...]
    stability: dict[str, object]
    sft: dict[str, object]


def build_system_smoke_report(
    plan_path: Path = DEFAULT_PLAN_PATH,
    *,
    require_training_dependencies: bool = False,
    dependency_names: Sequence[str] = REQUIRED_TRAINING_MODULES,
) -> SystemSmokeReport:
    """Validate the current checkout can reach the FT execution boundary."""

    sft_report = build_dry_run_report(plan_path, dependency_names=dependency_names)
    runtime_profile = build_runtime_profile(disk_path=Path.cwd())
    stability_report = run_stability_smoke()
    runtime_ready = all(
        check.status == "ready" for check in runtime_profile.constraint_checks
    )
    stability_smoke_ready = stability_report.get("status") == "stability_smoke_passed"
    errors: list[str] = []
    if not runtime_ready:
        errors.append("one or more selected runtime models are not ready")
    if not stability_smoke_ready:
        errors.append("stability smoke did not pass")
    if not sft_report.should_train:
        errors.append("SFT training plan is not ready")
    if require_training_dependencies and sft_report.missing_optional_dependencies:
        missing = ", ".join(sft_report.missing_optional_dependencies)
        errors.append(f"missing optional training dependencies: {missing}")

    return SystemSmokeReport(
        status="system_smoke_failed" if errors else "system_smoke_passed",
        runtime_ready=runtime_ready,
        training_plan_ready=sft_report.should_train,
        training_execute_ready=sft_report.execute_ready,
        stability_smoke_ready=stability_smoke_ready,
        missing_optional_dependencies=sft_report.missing_optional_dependencies,
        errors=tuple(errors),
        stability=stability_report,
        sft=dry_run_report_to_dict(sft_report),
    )


def system_smoke_report_to_dict(report: SystemSmokeReport) -> dict[str, object]:
    """Return a JSON-friendly smoke report."""

    payload = asdict(report)
    payload["missing_optional_dependencies"] = list(report.missing_optional_dependencies)
    payload["errors"] = list(report.errors)
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument(
        "--require-training-dependencies",
        action="store_true",
        help="fail unless optional FT dependencies are installed",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = build_system_smoke_report(
        args.plan,
        require_training_dependencies=args.require_training_dependencies,
    )
    print(json.dumps(system_smoke_report_to_dict(report), ensure_ascii=False, indent=2))
    return 0 if report.status == "system_smoke_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
