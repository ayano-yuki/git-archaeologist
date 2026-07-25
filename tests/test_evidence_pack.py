from __future__ import annotations

from datetime import datetime, timezone
import json
import unittest

from git_archaeologist.evidence_pack import (
    EvidenceItem,
    EvidencePackViolation,
    EvidenceStrength,
    TargetCodeContext,
    build_evidence_pack,
    estimate_token_count,
)


class EvidencePackTests(unittest.TestCase):
    def test_builds_valid_pack_with_source_references(self) -> None:
        pack = build_evidence_pack(
            question="why was createRoot changed?",
            target=TargetCodeContext(
                file_path="packages/react-dom/client.js",
                symbol_id="symbol-createRoot",
                qualified_name="ReactDOM.createRoot",
            ),
            candidate_items=(
                _item("review-1", EvidenceStrength.DIRECT, 12),
                _item("commit-1", EvidenceStrength.RELATED, 8),
            ),
            token_budget=30,
        )

        self.assertEqual(2, len(pack.items))
        self.assertEqual(20, pack.total_tokens)
        self.assertTrue(pack.items[0].source_url.startswith("https://"))
        self.assertEqual("parent-review-1", pack.items[0].parent_event_id)
        self.assertIn("evidence-pack-", pack.pack_id)

    def test_token_budget_prefers_direct_evidence_and_omits_rest(self) -> None:
        pack = build_evidence_pack(
            question="risk?",
            target=TargetCodeContext(file_path="packages/react-dom/client.js"),
            candidate_items=(
                _item("weak", EvidenceStrength.WEAK, 5),
                _item("direct", EvidenceStrength.DIRECT, 7),
                _item("related", EvidenceStrength.RELATED, 6),
            ),
            token_budget=10,
        )

        self.assertEqual(["direct"], [item.source_id for item in pack.items])
        self.assertEqual({"related", "weak"}, {item.source_id for item in pack.omitted})
        self.assertLessEqual(pack.total_tokens, pack.token_budget)

    def test_invalid_source_url_is_rejected(self) -> None:
        with self.assertRaises(EvidencePackViolation):
            EvidenceItem(
                source_id="bad",
                parent_event_id="parent",
                source_url="not-a-url",
                artifact_kind="review",
                text="evidence",
                token_count=1,
                strength=EvidenceStrength.DIRECT,
            )

    def test_pack_is_json_serializable_and_reproducible(self) -> None:
        kwargs = {
            "question": "why?",
            "target": TargetCodeContext(file_path="packages/react-dom/client.js", commit_sha="abc1234"),
            "candidate_items": (_item("commit-1", EvidenceStrength.DIRECT, 3),),
            "token_budget": 10,
        }
        first = build_evidence_pack(**kwargs)
        second = build_evidence_pack(**kwargs)

        self.assertEqual(first.pack_id, second.pack_id)
        serialized = json.dumps(first.to_dict(), sort_keys=True)
        self.assertIn('"schema_version": 1', serialized)
        self.assertIn('"source_id": "commit-1"', serialized)

    def test_estimates_tokens_without_zero_count(self) -> None:
        self.assertEqual(1, estimate_token_count(""))
        self.assertEqual(3, estimate_token_count("one two three"))


def _item(source_id: str, strength: EvidenceStrength, token_count: int) -> EvidenceItem:
    return EvidenceItem(
        source_id=source_id,
        parent_event_id=f"parent-{source_id}",
        source_url=f"https://github.com/facebook/react/{source_id}",
        artifact_kind="review",
        text=f"{source_id} explains the change",
        token_count=token_count,
        strength=strength,
        occurred_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        file_path="packages/react-dom/client.js",
        route=("commit-abc1234", source_id),
    )


if __name__ == "__main__":
    unittest.main()
