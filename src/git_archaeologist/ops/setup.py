"""Setup preflight for local Git Archaeologist operation."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from enum import StrEnum
import json
from pathlib import Path
from typing import Sequence

from git_archaeologist.collectors.gh_access import (
    GhRunner,
    check_github_access,
    run_gh_command,
)
from git_archaeologist.config.repository_config import (
    RepositoryConfig,
    load_builtin_repository_config,
    load_repository_config,
)
from git_archaeologist.config.storage_config import (
    DEFAULT_DATA_ROOT,
    build_application_stack,
    ensure_storage_layout,
)
from git_archaeologist.evaluation.production_training import (
    build_production_training_readiness,
)
from git_archaeologist.evaluation.runtime_profile import build_runtime_profile
from git_archaeologist.evaluation.train_sft import (
    DEFAULT_PLAN_PATH,
    REQUIRED_TRAINING_MODULES,
)
from git_archaeologist.ops.operations import build_local_operations_plan


class SetupMode(StrEnum):
    """Whether setup changes local directories."""

    DRY_RUN = "dry_run"
    EXECUTE = "execute"


class SetupCheckStatus(StrEnum):
    """Outcome for one setup preflight check."""

    READY = "ready"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class SetupCheck:
    """One setup check with safe operator-facing details."""

    check_id: str
    status: SetupCheckStatus
    required: bool
    reason: str
    details: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class LocalSetupReport:
    """Complete local setup preflight report."""

    status: str
    mode: SetupMode
    repository_id: str
    data_root: str
    training_execute_ready: bool
    checks: tuple[SetupCheck, ...]
    next_commands: tuple[str, ...]
    suppressed_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "next_commands", tuple(self.next_commands))
        object.__setattr__(self, "suppressed_fields", tuple(self.suppressed_fields))

    @property
    def passed(self) -> bool:
        return self.status == "local_setup_passed"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "mode": self.mode.value,
            "repository_id": self.repository_id,
            "data_root": self.data_root,
            "training_execute_ready": self.training_execute_ready,
            "checks": [check.to_dict() for check in self.checks],
            "next_commands": list(self.next_commands),
            "suppressed_fields": list(self.suppressed_fields),
        }


def build_local_setup_report(
    *,
    repository_id: str = "react/react",
    repository_config_path: Path | None = None,
    data_root: Path = DEFAULT_DATA_ROOT,
    plan_path: Path = DEFAULT_PLAN_PATH,
    mode: SetupMode = SetupMode.DRY_RUN,
    check_github: bool = True,
    require_training_dependencies: bool = False,
    gh_runner: GhRunner = run_gh_command,
) -> LocalSetupReport:
    """Build a setup report without leaking credentials or secret-like values."""

    checks: list[SetupCheck] = []
    config: RepositoryConfig | None = None

    try:
        config = (
            load_repository_config(repository_config_path)
            if repository_config_path is not None
            else load_builtin_repository_config(repository_id)
        )
    except Exception as exc:  # pragma: no cover - exact parser errors are tested elsewhere.
        checks.append(
            SetupCheck(
                check_id="repository_config",
                status=SetupCheckStatus.BLOCKED,
                required=True,
                reason="Repository configuration could not be loaded.",
                details={"error_type": type(exc).__name__, "error_message": str(exc)},
            )
        )
    else:
        checks.append(
            SetupCheck(
                check_id="repository_config",
                status=SetupCheckStatus.READY,
                required=True,
                reason="Repository configuration loaded and validated.",
                details={
                    "repository_id": config.repository_id,
                    "default_branch": config.default_branch,
                    "enabled_artifact_kinds": [kind.value for kind in config.enabled_artifact_kinds],
                },
            )
        )

    checks.append(_storage_check(data_root=data_root, mode=mode))

    if check_github and config is not None:
        checks.append(_github_access_check(config, gh_runner=gh_runner))
    else:
        checks.append(
            SetupCheck(
                check_id="github_access",
                status=SetupCheckStatus.SKIPPED,
                required=False,
                reason="GitHub access check was skipped.",
                details={"check_github": check_github},
            )
        )

    checks.append(_runtime_check(data_root=data_root))
    training_check = _production_training_check(
        data_root=data_root,
        plan_path=plan_path,
        require_training_dependencies=require_training_dependencies,
    )
    checks.append(training_check)
    checks.append(_initial_index_check(mode=mode))

    blocked_required = any(
        check.required and check.status is SetupCheckStatus.BLOCKED
        for check in checks
    )
    dry_run_details = training_check.details.get("dry_run")
    training_execute_ready = (
        bool(dry_run_details.get("execute_ready"))
        if isinstance(dry_run_details, dict)
        else False
    )
    plan = build_local_operations_plan(repository_id=repository_id)
    return LocalSetupReport(
        status="local_setup_blocked" if blocked_required else "local_setup_passed",
        mode=mode,
        repository_id=config.repository_id if config is not None else repository_id,
        data_root=str(data_root),
        training_execute_ready=training_execute_ready,
        checks=tuple(checks),
        next_commands=tuple(step.command for step in plan.all_steps),
        suppressed_fields=(
            "authorization_header",
            "raw_token",
            "secret_value",
            "private_key",
        ),
    )


def setup_report_to_json(report: LocalSetupReport) -> str:
    """Return a formatted JSON setup report."""

    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def _storage_check(*, data_root: Path, mode: SetupMode) -> SetupCheck:
    stack = build_application_stack(data_root)
    created_paths: tuple[str, ...] = ()
    if mode is SetupMode.EXECUTE:
        created_paths = tuple(path.as_posix() for path in ensure_storage_layout(data_root))
    return SetupCheck(
        check_id="storage_layout",
        status=SetupCheckStatus.READY,
        required=True,
        reason=(
            "Storage layout is described; directories were created."
            if mode is SetupMode.EXECUTE
            else "Storage layout is described; dry-run did not create directories."
        ),
        details={
            "profile_id": stack.profile_id,
            "data_root": stack.data_root,
            "component_roles": [component.role.value for component in stack.components],
            "created_paths": list(created_paths),
        },
    )


def _github_access_check(config: RepositoryConfig, *, gh_runner: GhRunner) -> SetupCheck:
    report = check_github_access(config, runner=gh_runner)
    return SetupCheck(
        check_id="github_access",
        status=SetupCheckStatus.READY if report.passed else SetupCheckStatus.BLOCKED,
        required=True,
        reason=(
            "gh authentication and repository read access passed."
            if report.passed
            else "gh authentication or repository read access failed before setup can run safely."
        ),
        details={
            "repository_id": report.repository_id,
            "passed": report.passed,
            "checked": [
                {
                    "kind": check.kind.value,
                    "target": check.target,
                    "operation": check.operation,
                    "passed": check.passed,
                }
                for check in report.checks
            ],
            "failures": list(report.human_payloads()),
        },
    )


def _runtime_check(*, data_root: Path) -> SetupCheck:
    profile = build_runtime_profile(disk_path=data_root.parent if data_root.parent else Path.cwd())
    blocked = [
        check
        for check in profile.constraint_checks
        if check.status == "blocked"
    ]
    return SetupCheck(
        check_id="runtime_profile",
        status=SetupCheckStatus.BLOCKED if blocked else SetupCheckStatus.READY,
        required=True,
        reason=(
            "Runtime profile has no blocked model constraints."
            if not blocked
            else "One or more model constraints are blocked on this machine."
        ),
        details={
            "profile_id": profile.profile_id,
            "constraint_checks": [
                {
                    "role": check.role.value,
                    "model_id": check.model_id,
                    "status": check.status,
                    "reason": check.reason,
                }
                for check in profile.constraint_checks
            ],
        },
    )


def _production_training_check(
    *,
    data_root: Path,
    plan_path: Path,
    require_training_dependencies: bool,
) -> SetupCheck:
    dependency_names = REQUIRED_TRAINING_MODULES if require_training_dependencies else ()
    readiness = build_production_training_readiness(
        runs_root=data_root / "runs",
        plan_path=plan_path,
        dependency_names=dependency_names,
    )
    return SetupCheck(
        check_id="production_training_readiness",
        status=SetupCheckStatus.READY if readiness.ready else SetupCheckStatus.BLOCKED,
        required=False,
        reason=(
            "Production data and SFT plan are ready; execution readiness is reported separately."
            if readiness.ready
            else "Production training inputs are incomplete in the current data/dependency state."
        ),
        details=readiness.to_dict(),
    )


def _initial_index_check(*, mode: SetupMode) -> SetupCheck:
    return SetupCheck(
        check_id="initial_index_plan",
        status=SetupCheckStatus.READY,
        required=True,
        reason=(
            "Initial index orchestration is represented as a safe setup step; execution remains explicit."
            if mode is SetupMode.DRY_RUN
            else "Initial index orchestration was confirmed; no external collection was run by setup."
        ),
        details={
            "dry_run_command": "uv --system-certs run python -m git_archaeologist.ops.setup --dry-run",
            "storage_init_command": "uv --system-certs run python -m git_archaeologist.config.storage_config --init",
            "external_collection_executed": False,
        },
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="validate setup without creating directories")
    mode.add_argument("--execute", action="store_true", help="create local storage directories after validation")
    parser.add_argument("--repository-id", default="react/react")
    parser.add_argument("--repository-config", type=Path, default=None)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--skip-github-access", action="store_true")
    parser.add_argument("--require-training-dependencies", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    mode = SetupMode.EXECUTE if args.execute else SetupMode.DRY_RUN
    report = build_local_setup_report(
        repository_id=args.repository_id,
        repository_config_path=args.repository_config,
        data_root=args.data_root,
        plan_path=args.plan,
        mode=mode,
        check_github=not args.skip_github_access,
        require_training_dependencies=args.require_training_dependencies,
    )
    print(setup_report_to_json(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
