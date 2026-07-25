from __future__ import annotations

import unittest

from git_archaeologist.phase4_smoke import run_phase4_smoke
from git_archaeologist.rag.lineage_answering import (
    LineageAnswerStatus,
    build_lineage_answer,
)
from git_archaeologist.search.lineage_analysis import (
    ConditionChangeKind,
    LineageRelationKind,
    LineRange,
    build_condition_history_entry,
    classify_condition_change,
    content_fingerprint,
    detect_file_lineage,
    detect_symbol_lineage,
    parse_blame_porcelain,
    separate_rationale,
)


class Phase4LineageTests(unittest.TestCase):
    def test_blame_porcelain_returns_line_origin_candidates(self) -> None:
        candidates = parse_blame_porcelain(
            "abc1234 10 20 1\nboundary\n\tline\n",
            file_path="a.js",
            requested_start=20,
            requested_end=20,
        )

        self.assertEqual(1, len(candidates))
        self.assertEqual("abc1234", candidates[0].commit_sha)
        self.assertEqual(LineRange("a.js", 20, 20), candidates[0].current_range)
        self.assertLess(candidates[0].confidence, 1.0)

    def test_file_lineage_detects_rename_move_and_copy(self) -> None:
        renamed = detect_file_lineage(source_path="a.js", target_path="b.js", source_content="const x = 1", target_content="const x = 1", explicit_rename=True)
        copied = detect_file_lineage(source_path="a.js", target_path="b.js", source_content="function createRoot(){ return guard && value; }", target_content="function createRootCopy(){ return guard && value; }")

        self.assertEqual(LineageRelationKind.RENAMED, renamed.relation_kind)
        self.assertIn(copied.relation_kind, {LineageRelationKind.MOVED, LineageRelationKind.COPIED})

    def test_symbol_lineage_handles_rename_and_unknown(self) -> None:
        renamed = detect_symbol_lineage(source_symbol="oldName", target_symbol="newName", source_body="return guard && value", target_body="return guard && value")
        unknown = detect_symbol_lineage(source_symbol="oldName", target_symbol="newName", source_body="return a", target_body="throw error")

        self.assertEqual(LineageRelationKind.RENAMED, renamed.relation_kind)
        self.assertEqual(LineageRelationKind.UNKNOWN, unknown.relation_kind)

    def test_condition_history_distinguishes_semantic_changes(self) -> None:
        self.assertEqual(ConditionChangeKind.FORMAT_ONLY, classify_condition_change("a && b", "a&&b"))
        self.assertEqual(ConditionChangeKind.NEGATED, classify_condition_change("a", "!a"))
        entry = build_condition_history_entry(
            commit_sha="abc1234",
            file_path="a.js",
            symbol_name="guard",
            before_expression="a",
            after_expression="a && b",
            branch_body_excerpt="return",
            related_tests=("guard.test",),
        )

        self.assertEqual(ConditionChangeKind.EXTENDED, entry.change_kind)
        self.assertEqual(("guard.test",), entry.related_tests)

    def test_rationale_and_answer_preserve_ambiguity(self) -> None:
        candidates = parse_blame_porcelain(
            "abc1234 10 20 1\n\tline\n"
            "def5678 30 20 1\n\tline\n",
            file_path="a.js",
            requested_start=20,
            requested_end=20,
        )
        answer = build_lineage_answer(
            origin_candidates=candidates,
            rationale=separate_rationale(
                introduction_evidence="introduced by review",
                maintenance_evidence=None,
                current_state="unknown",
            ),
        )

        self.assertEqual(LineageAnswerStatus.AMBIGUOUS, answer.status)
        self.assertIsNotNone(answer.missing_information)

    def test_content_fingerprint_normalizes_whitespace(self) -> None:
        self.assertEqual(content_fingerprint("return  value"), content_fingerprint("return value"))

    def test_phase4_smoke_passes(self) -> None:
        self.assertEqual("phase4_smoke_passed", run_phase4_smoke()["status"])


if __name__ == "__main__":
    unittest.main()
