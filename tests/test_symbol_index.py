from __future__ import annotations

import json
import unittest

from git_archaeologist.symbol_index import (
    SymbolIndex,
    SymbolMatchKind,
    SymbolRange,
    SymbolRecord,
    stable_symbol_id,
    symbol_index_to_dict,
)


class SymbolIndexTests(unittest.TestCase):
    def test_finds_symbols_by_file_and_symbol_name(self) -> None:
        index = SymbolIndex((_record("React.createRoot", "packages/react-dom/client.js"),))

        by_file = index.find_by_file("packages/react-dom/client.js")
        by_symbol = index.find_by_symbol("createRoot")

        self.assertEqual(1, len(by_file))
        self.assertEqual(SymbolMatchKind.FILE_MATCH, by_file[0].match_kind)
        self.assertEqual(1, len(by_symbol))
        self.assertEqual("abc1234", by_symbol[0].record.commit_sha)

    def test_symbol_id_is_stable_for_same_revision(self) -> None:
        record = _record("React.use", "packages/react/src/ReactHooks.js")

        self.assertEqual(stable_symbol_id(record), stable_symbol_id(record))
        self.assertEqual(stable_symbol_id(record), record.symbol_id)

    def test_connects_symbol_to_commit_sha_and_content_hash(self) -> None:
        record = _record("React.use", "packages/react/src/ReactHooks.js")
        payload = record.to_dict()

        self.assertEqual("abc1234", payload["commit_sha"])
        self.assertEqual("sha256:content", payload["content_hash"])
        self.assertEqual({"start_line": 10, "end_line": 20}, payload["range"])

    def test_rename_returns_candidate_without_guessing(self) -> None:
        index = SymbolIndex(
            (
                _record(
                    "React.use",
                    "packages/react/src/ReactHooks.js",
                    previous_file_path="packages/react/src/ReactOldHooks.js",
                ),
            )
        )

        candidates = index.find_by_file("packages/react/src/ReactOldHooks.js")

        self.assertEqual(1, len(candidates))
        self.assertEqual(SymbolMatchKind.RENAMED_FILE_MATCH, candidates[0].match_kind)
        self.assertIn("previous_file_path", candidates[0].ambiguity_reason or "")

    def test_unsupported_language_returns_explicit_candidate(self) -> None:
        index = SymbolIndex(())
        candidate = index.unsupported_for_file("src/native.mm", "outside MVP parser policy")

        self.assertEqual(SymbolMatchKind.UNSUPPORTED_LANGUAGE, candidate.match_kind)
        self.assertEqual(0.0, candidate.score)
        self.assertEqual("outside MVP parser policy", candidate.record.unsupported_reason)

    def test_index_payload_is_json_serializable(self) -> None:
        payload = symbol_index_to_dict(SymbolIndex((_record("React.use", "file.js"),)))
        serialized = json.dumps(payload, sort_keys=True)

        self.assertIn('"schema_version": 1', serialized)
        self.assertIn('"qualified_name": "React.use"', serialized)


def _record(
    qualified_name: str,
    file_path: str,
    *,
    previous_file_path: str | None = None,
) -> SymbolRecord:
    return SymbolRecord(
        qualified_name=qualified_name,
        file_path=file_path,
        language="javascript",
        commit_sha="abc1234",
        content_hash="sha256:content",
        symbol_range=SymbolRange(start_line=10, end_line=20),
        previous_file_path=previous_file_path,
    )


if __name__ == "__main__":
    unittest.main()
