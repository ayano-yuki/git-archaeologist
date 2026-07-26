from __future__ import annotations

from dataclasses import dataclass
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from git_archaeologist.collectors.gh_access import GhCommandResult
from git_archaeologist.evaluation.runtime_profile import ModelRole
from git_archaeologist.ops.phase5_setup import (
    SetupCheckStatus,
    SetupMode,
    build_phase5_setup_report,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/baseline-rag/sft/answer-discipline/lora-training-plan.json"


@dataclass(frozen=True)
class _Check:
    role: ModelRole
    model_id: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    status: str = "ready"
    reason: str = "ready"


@dataclass(frozen=True)
class _Profile:
    profile_id: str = "test-profile"
    constraint_checks: tuple[_Check, ...] = (_Check(ModelRole.ANSWER_JUDGE),)


def _gh_success(command):
    if command[:3] == ("gh", "auth", "status"):
        return GhCommandResult(returncode=0, stdout="Logged in")
    if command[:3] == ("gh", "repo", "view"):
        return GhCommandResult(returncode=0, stdout='{"nameWithOwner":"react/react"}')
    if command[:3] == ("gh", "pr", "list"):
        return GhCommandResult(returncode=0, stdout="[]")
    if command[:3] == ("gh", "issue", "list"):
        return GhCommandResult(returncode=0, stdout="[]")
    if command[:3] == ("gh", "run", "list"):
        return GhCommandResult(returncode=0, stdout="[]")
    if command[:2] == ("gh", "api") and "pulls?state=all" in command[2]:
        return GhCommandResult(returncode=0, stdout='[{"number":1}]')
    if command[:2] == ("gh", "api") and "reviews" in command[2]:
        return GhCommandResult(returncode=0, stdout="[]")
    raise AssertionError(f"unexpected gh command: {command}")


def _gh_auth_failure(command):
    if command[:3] == ("gh", "auth", "status"):
        return GhCommandResult(returncode=1, stderr="not logged in; raw_token=secret")
    raise AssertionError("setup should stop gh checks after auth failure")


class Phase5SetupTests(unittest.TestCase):
    def test_dry_run_passes_with_safe_fake_github_access(self) -> None:
        with patch(
            "git_archaeologist.ops.phase5_setup.build_runtime_profile",
            return_value=_Profile(),
        ):
            report = build_phase5_setup_report(
                plan_path=PLAN_PATH,
                mode=SetupMode.DRY_RUN,
                gh_runner=_gh_success,
            )

        self.assertEqual("phase5_setup_passed", report.status)
        self.assertEqual(SetupMode.DRY_RUN, report.mode)
        self.assertIn("raw_token", report.suppressed_fields)
        check_ids = {check.check_id for check in report.checks}
        self.assertIn("repository_config", check_ids)
        self.assertIn("github_access", check_ids)
        self.assertIn("initial_index_plan", check_ids)

    def test_execute_creates_storage_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "git_archaeologist.ops.phase5_setup.build_runtime_profile",
            return_value=_Profile(),
        ):
            data_root = Path(temp_dir) / "local-runtime"
            report = build_phase5_setup_report(
                plan_path=PLAN_PATH,
                data_root=data_root,
                mode=SetupMode.EXECUTE,
                check_github=False,
            )

            self.assertTrue((data_root / "raw").is_dir())
            self.assertTrue((data_root / "processed").is_dir())

        storage_check = next(check for check in report.checks if check.check_id == "storage_layout")
        self.assertEqual(SetupCheckStatus.READY, storage_check.status)
        self.assertTrue(storage_check.details["created_paths"])

    def test_github_failure_is_blocking_and_redacted_to_human_payload(self) -> None:
        with patch(
            "git_archaeologist.ops.phase5_setup.build_runtime_profile",
            return_value=_Profile(),
        ):
            report = build_phase5_setup_report(
                plan_path=PLAN_PATH,
                mode=SetupMode.DRY_RUN,
                gh_runner=_gh_auth_failure,
            )

        self.assertEqual("phase5_setup_blocked", report.status)
        github_check = next(check for check in report.checks if check.check_id == "github_access")
        self.assertEqual(SetupCheckStatus.BLOCKED, github_check.status)
        serialized = str(github_check.details)
        self.assertIn("authentication", serialized)
        self.assertNotIn("raw_token=secret", serialized)

    def test_can_skip_github_access_for_offline_setup_inspection(self) -> None:
        with patch(
            "git_archaeologist.ops.phase5_setup.build_runtime_profile",
            return_value=_Profile(),
        ):
            report = build_phase5_setup_report(
                plan_path=PLAN_PATH,
                mode=SetupMode.DRY_RUN,
                check_github=False,
            )

        github_check = next(check for check in report.checks if check.check_id == "github_access")
        self.assertEqual(SetupCheckStatus.SKIPPED, github_check.status)
        self.assertTrue(report.passed)


if __name__ == "__main__":
    unittest.main()
