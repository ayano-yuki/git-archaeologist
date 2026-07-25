from __future__ import annotations

from datetime import datetime, timezone
import unittest

from git_archaeologist.answer_schema import (
    AnswerClaim,
    AnswerVerdict,
    Citation,
    Confidence,
    StructuredAnswer,
)
from git_archaeologist.citation_verifier import (
    CitationVerificationStatus,
    verify_answer_citations,
)
from git_archaeologist.evidence_pack import (
    EvidenceItem,
    EvidencePack,
    EvidenceStrength,
    TargetCodeContext,
)


class CitationVerifierTests(unittest.TestCase):
    def test_supported_claim_passes_when_source_exists_and_text_overlaps(self) -> None:
        report = verify_answer_citations(answer=_answer("The review required a guard.", "review-1"), evidence_pack=_pack())

        self.assertTrue(report.is_supported)
        self.assertEqual(CitationVerificationStatus.SUPPORTED, report.claim_results[0].status)

    def test_missing_citation_is_reported(self) -> None:
        answer = StructuredAnswer(
            verdict=AnswerVerdict.RISK_FOUND,
            confirmed_reasons=(AnswerClaim("The change is risky.", ("review-1",)),),
            evidence=(Citation("review-1", "https://github.com/facebook/react/pull/1#discussion_r1", "review required guard"),),
            potential_risks=(AnswerClaim("Uncited risk claim."),),
            confidence=Confidence.MEDIUM,
        )

        report = verify_answer_citations(answer=answer, evidence_pack=_pack())

        self.assertEqual(CitationVerificationStatus.MISSING_CITATION, report.claim_results[1].status)
        self.assertFalse(report.is_supported)

    def test_unknown_source_is_reported(self) -> None:
        answer = _answer("The review required a guard.", "missing")

        report = verify_answer_citations(answer=answer, evidence_pack=_pack())

        self.assertEqual(CitationVerificationStatus.UNKNOWN_SOURCE, report.claim_results[0].status)

    def test_url_mismatch_is_reported(self) -> None:
        answer = StructuredAnswer(
            verdict=AnswerVerdict.EXPLAINED,
            confirmed_reasons=(AnswerClaim("The review required a guard.", ("review-1",)),),
            evidence=(Citation("review-1", "https://example.com/wrong", "review required guard"),),
            confidence=Confidence.HIGH,
        )

        report = verify_answer_citations(answer=answer, evidence_pack=_pack())

        self.assertEqual(CitationVerificationStatus.SOURCE_URL_MISMATCH, report.claim_results[0].status)

    def test_weak_support_and_temporal_conflict_are_reported(self) -> None:
        weak = verify_answer_citations(answer=_answer("Scheduler package metadata changed.", "review-1"), evidence_pack=_pack())
        temporal = verify_answer_citations(answer=_answer("The review happened in 2025.", "review-1"), evidence_pack=_pack())

        self.assertEqual(CitationVerificationStatus.WEAK_SUPPORT, weak.claim_results[0].status)
        self.assertEqual(CitationVerificationStatus.TEMPORAL_CONFLICT, temporal.claim_results[0].status)


def _answer(claim_text: str, source_id: str) -> StructuredAnswer:
    return StructuredAnswer(
        verdict=AnswerVerdict.EXPLAINED,
        confirmed_reasons=(AnswerClaim(claim_text, (source_id,)),),
        evidence=(Citation(source_id, "https://github.com/facebook/react/pull/1#discussion_r1", "review required guard"),),
        confidence=Confidence.HIGH,
    )


def _pack() -> EvidencePack:
    return EvidencePack(
        question="why?",
        target=TargetCodeContext(file_path="packages/react-dom/client.js"),
        items=(
            EvidenceItem(
                source_id="review-1",
                parent_event_id="pr-1",
                source_url="https://github.com/facebook/react/pull/1#discussion_r1",
                artifact_kind="review_comment",
                text="The reviewer required a guard before landing createRoot.",
                token_count=8,
                strength=EvidenceStrength.DIRECT,
                occurred_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            ),
        ),
        omitted=(),
        token_budget=20,
        total_tokens=8,
        pack_id="pack-1",
    )


if __name__ == "__main__":
    unittest.main()
