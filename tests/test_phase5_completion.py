from __future__ import annotations

import unittest

from git_archaeologist.evaluation.phase5_regression import PHASE5_REGRESSION_SUITE_ID
from git_archaeologist.ops.phase5_operations import build_phase5_regression_suite_plan


class Phase5CompletionTests(unittest.TestCase):
    def test_phase5_regression_operation_exposes_cli_suite(self) -> None:
        plan = build_phase5_regression_suite_plan()

        self.assertEqual(PHASE5_REGRESSION_SUITE_ID, plan.suite_id)
        self.assertEqual(1, len(plan.commands))
        self.assertIn("git_archaeologist.evaluation.phase5_regression", plan.commands[0])
        self.assertIn(f"--suite {PHASE5_REGRESSION_SUITE_ID}", plan.commands[0])
        self.assertTrue(plan.required_reports)

    def test_phase5_regression_plan_keeps_heavy_model_execution_out_of_default(self) -> None:
        plan = build_phase5_regression_suite_plan()
        command_text = "\n".join(plan.commands)

        self.assertNotIn("train_sft --execute", command_text)
        self.assertNotIn("--extra training", command_text)
        self.assertNotIn("gh ", command_text)


if __name__ == "__main__":
    unittest.main()
