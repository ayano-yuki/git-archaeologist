from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unittest
from unittest.mock import patch

from git_archaeologist.evaluation.runtime_profile import ModelRole
from git_archaeologist.evaluation.system_smoke import (
    build_system_smoke_report,
    system_smoke_report_to_dict,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/baseline-rag/sft/answer-discipline/lora-training-plan.json"


@dataclass(frozen=True)
class _Check:
    role: ModelRole
    status: str
    reason: str = "ready"


@dataclass(frozen=True)
class _Profile:
    constraint_checks: tuple[_Check, ...]


class SystemSmokeTests(unittest.TestCase):
    def test_system_smoke_passes_when_runtime_and_sft_plan_are_ready(self) -> None:
        fake_profile = _Profile(
            constraint_checks=(_Check(role=ModelRole.ANSWER_JUDGE, status="ready"),)
        )
        with patch("git_archaeologist.evaluation.system_smoke.build_runtime_profile", return_value=fake_profile), patch(
            "git_archaeologist.evaluation.train_sft.build_runtime_profile",
            return_value=fake_profile,
        ):
            report = build_system_smoke_report(PLAN_PATH, dependency_names=())

        self.assertEqual("system_smoke_passed", report.status)
        self.assertTrue(report.runtime_ready)
        self.assertTrue(report.training_plan_ready)
        self.assertTrue(report.training_execute_ready)

    def test_system_smoke_can_require_training_dependencies(self) -> None:
        fake_profile = _Profile(
            constraint_checks=(_Check(role=ModelRole.ANSWER_JUDGE, status="ready"),)
        )
        with patch("git_archaeologist.evaluation.system_smoke.build_runtime_profile", return_value=fake_profile), patch(
            "git_archaeologist.evaluation.train_sft.build_runtime_profile",
            return_value=fake_profile,
        ):
            report = build_system_smoke_report(
                PLAN_PATH,
                require_training_dependencies=True,
                dependency_names=("definitely_missing_training_runtime",),
            )

        payload = system_smoke_report_to_dict(report)
        self.assertEqual("system_smoke_failed", report.status)
        self.assertIn("definitely_missing_training_runtime", payload["errors"][0])


if __name__ == "__main__":
    unittest.main()
