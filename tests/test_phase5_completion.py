from __future__ import annotations

import unittest

from git_archaeologist.ops.phase5_operations import build_phase5_operations_report


class Phase5CompletionTests(unittest.TestCase):
    def test_phase5_operations_include_data_protection_before_training_cleanup(self) -> None:
        report = build_phase5_operations_report()
        commands = " ".join(report.data_protection_commands)

        self.assertIn("git_archaeologist.ops.data_protection --inventory", commands)
        self.assertIn("git_archaeologist.ops.data_protection --backup-plan", commands)
        self.assertIn("git_archaeologist.ops.data_protection --delete-plan", commands)


if __name__ == "__main__":
    unittest.main()
