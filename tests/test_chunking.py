from __future__ import annotations

import json
import unittest

from git_archaeologist.rag.chunking import (
    ChunkKind,
    chunk_commit_message,
    chunk_diff_hunk,
    chunk_text_artifact,
)


class ChunkingTests(unittest.TestCase):
    def test_short_commit_message_stays_traceable_to_parent_event(self) -> None:
        chunks = chunk_commit_message(
            parent_event_id="event-git_commit-1",
            source_url="https://github.com/react/react/commit/abc1234",
            subject="Fix scheduler regression",
            occurred_at="2026-07-26T00:00:00Z",
        )

        self.assertEqual(1, len(chunks))
        self.assertEqual(ChunkKind.COMMIT_MESSAGE, chunks[0].chunk_kind)
        self.assertEqual("event-git_commit-1", chunks[0].parent_event_id)
        self.assertEqual("https://github.com/react/react/commit/abc1234", chunks[0].source_url)
        self.assertEqual("Fix scheduler regression", chunks[0].text)

    def test_long_comment_splits_on_paragraph_boundary_with_context(self) -> None:
        text = "\n\n".join(
            [
                "First paragraph explains the historical decision.",
                "Second paragraph carries a review constraint.",
                "Third paragraph mentions the risk.",
            ]
        )

        chunks = chunk_text_artifact(
            chunk_kind=ChunkKind.REVIEW_COMMENT,
            parent_event_id="event-review-1",
            source_url="https://github.com/react/react/pull/1#discussion_r1",
            text=text,
            max_chars=80,
        )

        self.assertEqual(3, len(chunks))
        self.assertIsNone(chunks[0].previous_context)
        self.assertIn("Second paragraph", chunks[0].next_context)
        self.assertIn("First paragraph", chunks[1].previous_context)

    def test_diff_hunk_preserves_file_path_and_hunk_header(self) -> None:
        hunk = "\n".join(
            [
                "@@ -1,2 +1,3 @@",
                " const value = 1;",
                "+const guard = true;",
                "@@ -10,2 +11,3 @@",
                "-old();",
                "+new();",
            ]
        )

        chunks = chunk_diff_hunk(
            parent_event_id="event-commit-1",
            source_url="https://github.com/react/react/commit/abc1234",
            hunk=hunk,
            file_path="packages/react/src/file.js",
            max_chars=120,
        )

        self.assertEqual(2, len(chunks))
        self.assertTrue(chunks[0].text.startswith("@@ -1,2"))
        self.assertEqual("packages/react/src/file.js", chunks[0].metadata["file_path"])

    def test_chunk_payload_is_json_serializable(self) -> None:
        chunk = chunk_commit_message(
            parent_event_id="event-git_commit-1",
            source_url="https://github.com/react/react/commit/abc1234",
            subject="Fix scheduler regression",
        )[0]

        serialized = json.dumps(chunk.to_dict(), sort_keys=True)

        self.assertIn('"chunk_kind": "commit_message"', serialized)
        self.assertIn('"parent_event_id": "event-git_commit-1"', serialized)

    def test_rejects_untraceable_source_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_url"):
            chunk_commit_message(
                parent_event_id="event-git_commit-1",
                source_url="not-a-url",
                subject="Fix scheduler regression",
            )


if __name__ == "__main__":
    unittest.main()
