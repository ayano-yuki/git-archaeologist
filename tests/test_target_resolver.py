from __future__ import annotations

import unittest

from git_archaeologist.search.code_snippet_resolver import CodeDocument
from git_archaeologist.search.symbol_index import SymbolIndex, SymbolRange, SymbolRecord
from git_archaeologist.search.target_resolver import (
    GitLogMatch,
    TargetKind,
    TargetRequest,
    TargetResolutionStatus,
    parse_pull_request_url,
    resolve_target,
)


class TargetResolverTests(unittest.TestCase):
    def test_parses_pr_url_as_high_confidence_target(self) -> None:
        reference = parse_pull_request_url("please inspect https://github.com/facebook/react/pull/12345")
        resolution = resolve_target(
            TargetRequest(raw_text="https://github.com/facebook/react/pull/12345"),
        )

        self.assertEqual("facebook/react#12345", reference.identifier)
        self.assertEqual(TargetResolutionStatus.RESOLVED, resolution.status)
        self.assertEqual(TargetKind.PULL_REQUEST, resolution.selected_candidate.target_kind)
        self.assertTrue(resolution.should_generate_answer)

    def test_resolves_file_path_from_current_documents(self) -> None:
        resolution = resolve_target(
            TargetRequest(raw_text="why", file_path="packages/react-dom/client.js"),
            current_documents=(
                CodeDocument("client", "packages/react-dom/client.js", "export function createRoot() {}", "abc1234"),
            ),
        )

        self.assertEqual(TargetResolutionStatus.RESOLVED, resolution.status)
        self.assertEqual("packages/react-dom/client.js", resolution.selected_candidate.file_path)
        self.assertIn("current code", resolution.selected_candidate.reason)

    def test_resolves_symbol_from_symbol_index(self) -> None:
        resolution = resolve_target(
            TargetRequest(raw_text="why createRoot", symbol_name="createRoot"),
            symbol_index=_symbol_index(),
        )

        self.assertEqual(TargetResolutionStatus.RESOLVED, resolution.status)
        self.assertEqual(TargetKind.SYMBOL, resolution.selected_candidate.target_kind)
        self.assertEqual("ReactDOM.createRoot", resolution.selected_candidate.qualified_name)

    def test_resolves_code_snippet_with_existing_snippet_resolver(self) -> None:
        resolution = resolve_target(
            TargetRequest(raw_text="why", code_snippet="function createRoot()"),
            current_documents=(
                CodeDocument("client", "packages/react-dom/client.js", "export function createRoot() {}", "abc1234"),
            ),
        )

        self.assertEqual(TargetResolutionStatus.RESOLVED, resolution.status)
        self.assertEqual(TargetKind.CODE_SNIPPET, resolution.selected_candidate.target_kind)
        self.assertEqual("packages/react-dom/client.js", resolution.selected_candidate.file_path)

    def test_multiple_targets_require_clarification(self) -> None:
        resolution = resolve_target(
            TargetRequest(raw_text="why", file_path="packages/react-dom/client.js"),
            current_documents=(
                CodeDocument("a", "packages/react-dom/client.js", "one", "a1"),
                CodeDocument("b", "packages/react-dom/client.js", "two", "b2"),
            ),
        )

        self.assertEqual(TargetResolutionStatus.AMBIGUOUS, resolution.status)
        self.assertFalse(resolution.should_generate_answer)
        self.assertIn("choose", resolution.clarification_reason or "")

    def test_git_log_string_fallback_records_reason(self) -> None:
        resolution = resolve_target(
            TargetRequest(raw_text="why", git_log_string="removedLegacyRoot"),
            git_log_backend=_StubGitLogBackend(),
        )

        self.assertEqual(TargetResolutionStatus.RESOLVED, resolution.status)
        self.assertEqual(TargetKind.GIT_LOG_STRING, resolution.selected_candidate.target_kind)
        self.assertEqual("abc1234:packages/react-dom/client.js", resolution.selected_candidate.identifier)
        self.assertIn("git history", resolution.selected_candidate.reason)

    def test_unresolved_target_blocks_answer_generation(self) -> None:
        resolution = resolve_target(TargetRequest(raw_text="just a vague question"))

        self.assertEqual(TargetResolutionStatus.UNRESOLVED, resolution.status)
        self.assertFalse(resolution.should_generate_answer)
        self.assertIn("no PR URL", resolution.unresolved_reason or "")


class _StubGitLogBackend:
    def search_string(self, query: str) -> tuple[GitLogMatch, ...]:
        return (
            GitLogMatch(
                commit_sha="abc1234",
                file_path="packages/react-dom/client.js",
                query=query,
                mode=TargetKind.GIT_LOG_STRING,
                confidence=0.7,
            ),
        )

    def search_regex(self, query: str) -> tuple[GitLogMatch, ...]:
        return (
            GitLogMatch(
                commit_sha="def5678",
                file_path="packages/react-dom/client.js",
                query=query,
                mode=TargetKind.GIT_LOG_REGEX,
                confidence=0.65,
            ),
        )


def _symbol_index() -> SymbolIndex:
    return SymbolIndex(
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


if __name__ == "__main__":
    unittest.main()
