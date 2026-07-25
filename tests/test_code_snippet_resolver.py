from __future__ import annotations

import unittest

from git_archaeologist.code_snippet_resolver import (
    CodeDocument,
    ResolutionStatus,
    SnippetMatchKind,
    normalize_code,
    resolve_code_snippet,
)
from git_archaeologist.symbol_index import SymbolIndex, SymbolRange, SymbolRecord


class CodeSnippetResolverTests(unittest.TestCase):
    def test_exact_unique_candidate_is_auto_selected(self) -> None:
        resolution = resolve_code_snippet(
            "function useThing()",
            (_document("react-hooks", "packages/react/src/ReactHooks.js", "export function useThing() {}"),),
        )

        self.assertEqual(ResolutionStatus.RESOLVED, resolution.status)
        self.assertTrue(resolution.should_generate_answer)
        self.assertEqual(SnippetMatchKind.EXACT, resolution.selected_candidate.match_kind)

    def test_normalized_match_ignores_comments_and_whitespace(self) -> None:
        resolution = resolve_code_snippet(
            "function createRoot() { return root; }",
            (
                _document(
                    "dom-root",
                    "packages/react-dom/client.js",
                    "function createRoot() {\n  // DEV guard\n  return root;\n}",
                ),
            ),
        )

        self.assertEqual(ResolutionStatus.RESOLVED, resolution.status)
        self.assertEqual(SnippetMatchKind.NORMALIZED, resolution.selected_candidate.match_kind)
        self.assertEqual("function createRoot() { return root; }", normalize_code("function createRoot() {\n// x\nreturn root;\n}"))

    def test_multiple_equal_candidates_require_clarification(self) -> None:
        resolution = resolve_code_snippet(
            "const flag = shouldWarn && didScheduleUpdate;",
            (
                _document("a", "packages/a.js", "const flag = shouldWarn && didScheduleUpdate;"),
                _document("b", "packages/b.js", "const flag = shouldWarn && didScheduleUpdate;"),
            ),
        )

        self.assertEqual(ResolutionStatus.AMBIGUOUS, resolution.status)
        self.assertFalse(resolution.should_generate_answer)
        self.assertEqual(2, len(resolution.candidates))
        self.assertIn("clarification", resolution.ambiguity_reason or "")

    def test_unresolved_target_blocks_answer_generation(self) -> None:
        resolution = resolve_code_snippet(
            "function missingTarget() {}",
            (_document("a", "packages/a.js", "function knownTarget() {}"),),
        )

        self.assertEqual(ResolutionStatus.UNRESOLVED, resolution.status)
        self.assertFalse(resolution.should_generate_answer)
        self.assertIn("no exact", resolution.unresolved_reason or "")

    def test_symbol_index_is_used_after_text_matching_fails(self) -> None:
        index = SymbolIndex(
            (
                SymbolRecord(
                    qualified_name="ReactDOM.createRoot",
                    file_path="packages/react-dom/client.js",
                    language="javascript",
                    commit_sha="abc1234",
                    content_hash="sha256:content",
                    symbol_range=SymbolRange(10, 20),
                ),
            )
        )

        resolution = resolve_code_snippet(
            "why does createRoot warn here?",
            (_document("empty", "README.md", "no code here"),),
            symbol_index=index,
            lexical_threshold=0.9,
        )

        self.assertEqual(ResolutionStatus.RESOLVED, resolution.status)
        self.assertEqual(SnippetMatchKind.SYMBOL, resolution.selected_candidate.match_kind)
        self.assertEqual("ReactDOM.createRoot", resolution.selected_candidate.qualified_name)


def _document(document_id: str, file_path: str, content: str) -> CodeDocument:
    return CodeDocument(document_id=document_id, file_path=file_path, content=content)


if __name__ == "__main__":
    unittest.main()
