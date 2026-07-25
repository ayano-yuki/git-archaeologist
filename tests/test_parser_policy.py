from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from git_archaeologist.parser_policy import (  # noqa: E402
    PARSER_POLICY_ID,
    TARGET_REPOSITORY_ID,
    ParserBackend,
    ParserSupport,
    SymbolExtractionMode,
    classify_path,
    load_react_mvp_parser_policy,
    parser_policy_to_dict,
    supported_source_extensions,
)


class ParserPolicyTests(unittest.TestCase):
    def test_policy_targets_react_react_mvp(self) -> None:
        policy = load_react_mvp_parser_policy()

        self.assertEqual(PARSER_POLICY_ID, policy.policy_id)
        self.assertEqual(TARGET_REPOSITORY_ID, policy.repository_id)
        self.assertIn("LLMs must not infer", policy.no_llm_guessing_rule)

    def test_mvp_supports_typescript_javascript_jsx_and_tsx_symbols(self) -> None:
        extensions = supported_source_extensions()

        self.assertEqual({".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx"}, set(extensions))

        examples = {
            "packages/react/src/ReactHooks.js": "javascript",
            "packages/react-devtools-shared/src/backend/agent.js": "javascript",
            "fixtures/component.jsx": "jsx",
            "packages/react-dom/src/client/ReactDOMRoot.ts": "typescript",
            "packages/react-dom/src/client/ReactDOMRoot.tsx": "tsx",
        }
        for path, expected_language in examples.items():
            with self.subTest(path=path):
                decision = classify_path(path)

                self.assertEqual(ParserSupport.SYMBOLS_SUPPORTED, decision.support)
                self.assertEqual(ParserBackend.TREE_SITTER, decision.backend)
                self.assertEqual(SymbolExtractionMode.AST_SYMBOLS, decision.symbol_extraction)
                self.assertEqual(expected_language, decision.language_id)
                self.assertTrue(decision.can_extract_symbols)
                self.assertFalse(decision.fallback_required)
                self.assertTrue(decision.no_llm_guessing)

    def test_parser_unavailable_falls_back_to_file_snippet_and_hunk_level(self) -> None:
        policy = load_react_mvp_parser_policy()
        decision = classify_path(
            "packages/react/src/ReactHooks.js",
            parser_available=False,
            policy=policy,
        )

        self.assertEqual(ParserSupport.FILE_LEVEL_ONLY, decision.support)
        self.assertEqual(ParserBackend.FILE_LEVEL, decision.backend)
        self.assertEqual(SymbolExtractionMode.FILE_AND_SNIPPET_ONLY, decision.symbol_extraction)
        self.assertEqual("javascript", decision.language_id)
        self.assertFalse(decision.can_extract_symbols)
        self.assertTrue(decision.fallback_required)
        self.assertIn("parser is unavailable", decision.reason)
        self.assertIn("exact_code_snippet_match", policy.fallback_behavior.allowed_operations)
        self.assertIn("diff_hunk_match", policy.fallback_behavior.allowed_operations)
        self.assertIn("llm_guess_symbol_boundary", policy.fallback_behavior.disallowed_operations)

    def test_file_level_languages_do_not_extract_symbols(self) -> None:
        for path in ("package.json", ".github/workflows/ci.yml", "README.md"):
            with self.subTest(path=path):
                decision = classify_path(path)

                self.assertEqual(ParserSupport.FILE_LEVEL_ONLY, decision.support)
                self.assertEqual(ParserBackend.FILE_LEVEL, decision.backend)
                self.assertEqual(SymbolExtractionMode.FILE_AND_SNIPPET_ONLY, decision.symbol_extraction)
                self.assertFalse(decision.can_extract_symbols)
                self.assertFalse(decision.fallback_required)
                self.assertTrue(decision.no_llm_guessing)

    def test_unsupported_languages_are_rejected_for_symbol_indexing(self) -> None:
        for path in ("packages/react-dom/src/styles.css", "scripts/build.rs", "src/native.mm"):
            with self.subTest(path=path):
                decision = classify_path(path)

                self.assertEqual(ParserSupport.UNSUPPORTED, decision.support)
                self.assertEqual(ParserBackend.NONE, decision.backend)
                self.assertEqual(SymbolExtractionMode.REJECTED, decision.symbol_extraction)
                self.assertIsNone(decision.language_id)
                self.assertFalse(decision.can_extract_symbols)
                self.assertIn("Do not extract symbols", decision.reason)
                self.assertTrue(decision.no_llm_guessing)

    def test_policy_is_json_serializable(self) -> None:
        payload = parser_policy_to_dict()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertIn(PARSER_POLICY_ID, serialized)
        self.assertIn("supported_languages", payload)
        self.assertIn("unsupported_language_policy", payload)


if __name__ == "__main__":
    unittest.main()
