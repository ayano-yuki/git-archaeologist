from __future__ import annotations

import json
import unittest

from git_archaeologist.rag.answer_schema import (
    AnswerClaim,
    AnswerSchemaViolation,
    AnswerVerdict,
    Citation,
    Confidence,
    StructuredAnswer,
    safe_schema_error,
    validate_answer,
)


class AnswerSchemaTests(unittest.TestCase):
    def test_validates_structured_answer_with_fact_inference_and_missing_info(self) -> None:
        answer = _valid_answer()

        payload = validate_answer(answer.to_dict()).to_dict()

        self.assertEqual("explained", payload["verdict"])
        self.assertEqual("high", payload["confidence"])
        self.assertEqual("evidence-1", payload["confirmed_reasons"][0]["citation_ids"][0])
        self.assertEqual("This risk is inferred from the cited review.", payload["inferences"][0]["text"])
        self.assertEqual("No CI evidence was provided.", payload["missing_information"][0])

    def test_rejects_fact_claim_without_citation(self) -> None:
        with self.assertRaisesRegex(AnswerSchemaViolation, "must cite"):
            StructuredAnswer(
                verdict=AnswerVerdict.EXPLAINED,
                confirmed_reasons=(AnswerClaim(text="This is a fact."),),
                evidence=(
                    Citation(
                        source_id="evidence-1",
                        source_url="https://github.com/react/react/pull/1",
                        supports="review rationale",
                    ),
                ),
            )

    def test_rejects_unknown_citation_reference(self) -> None:
        with self.assertRaisesRegex(AnswerSchemaViolation, "unknown citation"):
            StructuredAnswer(
                verdict=AnswerVerdict.EXPLAINED,
                confirmed_reasons=(AnswerClaim(text="Fact.", citation_ids=("missing",)),),
                evidence=(
                    Citation(
                        source_id="evidence-1",
                        source_url="https://github.com/react/react/pull/1",
                        supports="review rationale",
                    ),
                ),
            )

    def test_requires_missing_information_for_insufficient_evidence(self) -> None:
        with self.assertRaisesRegex(AnswerSchemaViolation, "missing_information"):
            StructuredAnswer(
                verdict=AnswerVerdict.INSUFFICIENT_EVIDENCE,
                confirmed_reasons=(),
                evidence=(),
                confidence=Confidence.LOW,
            )

    def test_invalid_mapping_returns_safe_schema_error(self) -> None:
        try:
            validate_answer({"schema_version": 1})
        except AnswerSchemaViolation as exc:
            payload = safe_schema_error(exc)

        self.assertEqual("insufficient_evidence", payload["verdict"])
        self.assertEqual("low", payload["confidence"])
        self.assertIn("missing required field", payload["missing_information"][0])

    def test_payload_is_json_serializable(self) -> None:
        serialized = json.dumps(_valid_answer().to_dict(), sort_keys=True)

        self.assertIn('"schema_version": 1', serialized)
        self.assertIn('"verdict": "explained"', serialized)


def _valid_answer() -> StructuredAnswer:
    return StructuredAnswer(
        verdict=AnswerVerdict.EXPLAINED,
        confirmed_reasons=(
            AnswerClaim(
                text="The implementation was kept because review evidence required the guard.",
                citation_ids=("evidence-1",),
            ),
        ),
        evidence=(
            Citation(
                source_id="evidence-1",
                source_url="https://github.com/react/react/pull/1#discussion_r1",
                supports="review rationale",
            ),
        ),
        inferences=(
            AnswerClaim(
                text="This risk is inferred from the cited review.",
                citation_ids=("evidence-1",),
            ),
        ),
        potential_risks=(
            AnswerClaim(
                text="Removing the guard may reintroduce the reviewed behavior.",
                citation_ids=("evidence-1",),
            ),
        ),
        recommended_actions=("Check the same behavior in the current PR.",),
        missing_information=("No CI evidence was provided.",),
        confidence=Confidence.HIGH,
    )


if __name__ == "__main__":
    unittest.main()
