from __future__ import annotations

import copy
import unittest

from git_archaeologist.evaluation.sft_data_policy import (
    ALLOWED_TRAINING_CONTENT,
    COLLECTION_ERROR_CATEGORIES,
    EVAL_DATA_PATH_PATTERN,
    HUMAN_ERROR_REPORT_FIELDS,
    HUMAN_ERROR_SUPPRESSED_FIELDS,
    INITIAL_DATA_SOURCE_REPOSITORY,
    PROHIBITED_TRAINING_CONTENT,
    SFT_DATA_PATH_PATTERN,
    ExpectedVerdict,
    Split,
    validate_evaluation_case,
    validate_sft_record,
)


class SFTDataPolicyTests(unittest.TestCase):
    def test_policy_limits_sft_to_evidence_pack_answer_discipline(self) -> None:
        self.assertEqual(INITIAL_DATA_SOURCE_REPOSITORY, "react/react")
        self.assertEqual(SFT_DATA_PATH_PATTERN, "data/<model-name>/sft/")
        self.assertEqual(EVAL_DATA_PATH_PATTERN, "data/<model-name>/eval/")
        self.assertTrue(
            any("Evidence Packs" in item for item in ALLOWED_TRAINING_CONTENT)
        )
        self.assertTrue(
            any(
                "memorizing repository-specific facts" in item
                for item in PROHIBITED_TRAINING_CONTENT
            )
        )

    def test_collection_errors_define_human_report_payload(self) -> None:
        self.assertIn("auth_or_permission", COLLECTION_ERROR_CATEGORIES)
        self.assertIn("schema_or_parse_error", COLLECTION_ERROR_CATEGORIES)
        self.assertGreaterEqual(
            set(HUMAN_ERROR_REPORT_FIELDS),
            {
                "repository_id",
                "artifact_kind",
                "target",
                "operation",
                "error_type",
                "error_message",
                "source_url",
                "retry_count",
            },
        )
        self.assertIn("authorization_header", HUMAN_ERROR_SUPPRESSED_FIELDS)

    def test_validates_sample_sft_record_schema(self) -> None:
        record = validate_sft_record(_sample_sft_record())

        self.assertEqual(record.split, Split.TRAIN)
        self.assertEqual(record.question, "Why should this answer avoid guessing?")
        self.assertEqual(record.target["repository_id"], "react/react")
        self.assertEqual(
            record.ideal_answer["citations"],
            ["pr-1000-review-1"],
        )

    def test_rejects_sft_record_without_evidence_pack_items(self) -> None:
        raw_record = _sample_sft_record()
        raw_record["evidence_pack"]["evidence_items"] = []

        with self.assertRaisesRegex(ValueError, "must not be empty"):
            validate_sft_record(raw_record)

    def test_rejects_ideal_answer_with_unknown_citation(self) -> None:
        raw_record = _sample_sft_record()
        raw_record["ideal_answer"]["citations"] = ["missing-source"]

        with self.assertRaisesRegex(ValueError, "unknown source IDs"):
            validate_sft_record(raw_record)

    def test_validates_closed_book_leakage_eval_case(self) -> None:
        case = validate_evaluation_case(_closed_book_eval_case())

        self.assertTrue(case.is_closed_book_leakage_test)
        self.assertEqual(
            case.expected_behavior["verdict"], ExpectedVerdict.UNKNOWN.value
        )

    def test_empty_evidence_pack_eval_case_must_expect_unknown(self) -> None:
        raw_case = _closed_book_eval_case()
        raw_case["expected_behavior"]["verdict"] = "answerable"

        with self.assertRaisesRegex(ValueError, "must expect unknown"):
            validate_evaluation_case(raw_case)


def _sample_sft_record() -> dict[str, object]:
    return {
        "schema_version": 1,
        "record_id": "sft-react-react-0001",
        "source_repository": "react/react",
        "split": "train",
        "question": "Why should this answer avoid guessing?",
        "target": {
            "repository_id": "react/react",
            "target_type": "pull_request",
            "artifact_ids": ["pr-1000"],
        },
        "evidence_pack": {
            "pack_id": "ep-react-react-0001",
            "evidence_items": [
                {
                    "source_id": "pr-1000-review-1",
                    "artifact_kind": "review_comment",
                    "source_url": (
                        "https://github.com/react/react/pull/1000#discussion_r1"
                    ),
                    "excerpt": "Reviewer asks for a cited explanation before accepting.",
                }
            ],
        },
        "ideal_answer": {
            "answer": (
                "The answer should only state what the review supports and cite it."
            ),
            "citations": ["pr-1000-review-1"],
            "unsupported_claims": [],
            "confidence": "medium",
        },
        "labels": {
            "task": "review_judgment",
            "requires_abstention": False,
        },
    }


def _closed_book_eval_case() -> dict[str, object]:
    raw_record = copy.deepcopy(_sample_sft_record())
    return {
        "schema_version": 1,
        "case_id": "eval-react-react-closed-book-0001",
        "source_repository": "react/react",
        "split": "test",
        "question": "What did PR 1000 decide?",
        "target": raw_record["target"],
        "evidence_pack": {
            "pack_id": "ep-empty-0001",
            "evidence_items": [],
        },
        "expected_behavior": {
            "verdict": "unknown",
            "must_not_answer_closed_book": True,
            "required_answer_fragment": (
                "Evidence Pack does not contain enough evidence."
            ),
        },
    }


if __name__ == "__main__":
    unittest.main()
