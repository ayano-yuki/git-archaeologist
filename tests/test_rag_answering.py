from __future__ import annotations

from datetime import datetime, timezone
import unittest

from git_archaeologist.rag.evidence_pack import (
    EvidenceItem,
    EvidencePack,
    EvidenceStrength,
    TargetCodeContext,
    build_evidence_pack,
)
from git_archaeologist.rag.rag_answering import (
    RAG_SYSTEM_PROMPT_VERSION,
    RagModelConfig,
    answer_from_evidence_pack,
    build_rag_prompt_payload,
)


class RagAnsweringTests(unittest.TestCase):
    def test_prompt_payload_forbids_closed_book_repository_knowledge(self) -> None:
        pack = _pack()
        payload = build_rag_prompt_payload(
            evidence_pack=pack,
            model_config=RagModelConfig(model_version="local-model"),
        )

        serialized = payload.to_dict()
        self.assertIn("Evidence Pack", serialized["system_prompt"])
        self.assertIn("Do not use repository knowledge outside", serialized["system_prompt"])
        self.assertEqual(RAG_SYSTEM_PROMPT_VERSION, serialized["model_config"]["prompt_version"])
        self.assertEqual(pack.pack_id, serialized["evidence_pack"]["pack_id"])

    def test_valid_structured_answer_records_model_and_prompt_version(self) -> None:
        pack = _pack()
        result = answer_from_evidence_pack(
            evidence_pack=pack,
            model_config=RagModelConfig(model_version="judge-llm-v1"),
            backend=_SuccessfulBackend(),
        )

        self.assertEqual("judge-llm-v1", result.model_version)
        self.assertEqual(RAG_SYSTEM_PROMPT_VERSION, result.prompt_version)
        self.assertEqual(pack.pack_id, result.evidence_pack_id)
        self.assertEqual("explained", result.answer.to_dict()["verdict"])

    def test_missing_evidence_abstains_without_calling_backend(self) -> None:
        empty_pack = EvidencePack(
            question="why?",
            target=TargetCodeContext(file_path="packages/react-dom/client.js"),
            items=(),
            omitted=(),
            token_budget=10,
            total_tokens=0,
            pack_id="empty-pack",
        )

        result = answer_from_evidence_pack(
            evidence_pack=empty_pack,
            model_config=RagModelConfig(model_version="local-model"),
            backend=_FailIfCalledBackend(),
        )

        self.assertEqual("insufficient_evidence", result.answer.to_dict()["verdict"])
        self.assertIn("no items", result.answer.missing_information[0])


class _SuccessfulBackend:
    def generate(self, payload):
        item = payload.evidence_pack["items"][0]
        return {
            "schema_version": 1,
            "verdict": "explained",
            "confirmed_reasons": [
                {
                    "text": "The review explicitly required the guard.",
                    "citation_ids": [item["source_id"]],
                }
            ],
            "evidence": [
                {
                    "source_id": item["source_id"],
                    "source_url": item["source_url"],
                    "supports": "review required the guard",
                }
            ],
            "inferences": [],
            "potential_risks": [],
            "recommended_actions": [],
            "missing_information": [],
            "confidence": "high",
        }


class _FailIfCalledBackend:
    def generate(self, payload):
        raise AssertionError("backend should not be called")


def _pack():
    return build_evidence_pack(
        question="why was createRoot changed?",
        target=TargetCodeContext(file_path="packages/react-dom/client.js"),
        candidate_items=(
            EvidenceItem(
                source_id="review-1",
                parent_event_id="pr-1",
                source_url="https://github.com/facebook/react/pull/1#discussion_r1",
                artifact_kind="review_comment",
                text="The review explicitly required the guard.",
                token_count=8,
                strength=EvidenceStrength.DIRECT,
                occurred_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            ),
        ),
        token_budget=50,
    )


if __name__ == "__main__":
    unittest.main()
