"""Deterministic citation verification for structured answers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from git_archaeologist.rag.answer_schema import AnswerClaim, StructuredAnswer
from git_archaeologist.rag.evidence_pack import EvidenceItem, EvidencePack


class CitationVerificationStatus(StrEnum):
    """Verification status for one answer claim."""

    SUPPORTED = "supported"
    MISSING_CITATION = "missing_citation"
    UNKNOWN_SOURCE = "unknown_source"
    SOURCE_URL_MISMATCH = "source_url_mismatch"
    WEAK_SUPPORT = "weak_support"
    TEMPORAL_CONFLICT = "temporal_conflict"


@dataclass(frozen=True)
class ClaimVerification:
    """Verification result for one claim."""

    claim_text: str
    status: CitationVerificationStatus
    citation_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "citation_ids", tuple(self.citation_ids))


@dataclass(frozen=True)
class CitationVerificationReport:
    """Answer-level verification report."""

    pack_id: str
    claim_results: tuple[ClaimVerification, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_results", tuple(self.claim_results))

    @property
    def is_supported(self) -> bool:
        return all(result.status is CitationVerificationStatus.SUPPORTED for result in self.claim_results)


def verify_answer_citations(
    *,
    answer: StructuredAnswer,
    evidence_pack: EvidencePack,
    min_token_overlap: float = 0.2,
) -> CitationVerificationReport:
    """Verify citation existence, URL consistency, support, and simple temporal conflicts."""

    items_by_id = {item.source_id: item for item in evidence_pack.items}
    citation_urls = {citation.source_id: citation.source_url for citation in answer.evidence}
    results = [
        _verify_claim(
            claim,
            items_by_id=items_by_id,
            citation_urls=citation_urls,
            min_token_overlap=min_token_overlap,
        )
        for claim in (*answer.confirmed_reasons, *answer.potential_risks)
    ]
    return CitationVerificationReport(pack_id=evidence_pack.pack_id, claim_results=tuple(results))


def _verify_claim(
    claim: AnswerClaim,
    *,
    items_by_id: dict[str, EvidenceItem],
    citation_urls: dict[str, str],
    min_token_overlap: float,
) -> ClaimVerification:
    if not claim.citation_ids:
        return ClaimVerification(
            claim_text=claim.text,
            status=CitationVerificationStatus.MISSING_CITATION,
            citation_ids=(),
            reason="claim has no citation IDs",
        )

    cited_items: list[EvidenceItem] = []
    for citation_id in claim.citation_ids:
        item = items_by_id.get(citation_id)
        if item is None:
            return ClaimVerification(
                claim_text=claim.text,
                status=CitationVerificationStatus.UNKNOWN_SOURCE,
                citation_ids=claim.citation_ids,
                reason=f"citation source_id does not exist in Evidence Pack: {citation_id}",
            )
        if citation_urls.get(citation_id) != item.source_url:
            return ClaimVerification(
                claim_text=claim.text,
                status=CitationVerificationStatus.SOURCE_URL_MISMATCH,
                citation_ids=claim.citation_ids,
                reason=f"citation source_url does not match Evidence Pack item: {citation_id}",
            )
        cited_items.append(item)

    if _has_temporal_conflict(claim.text, tuple(cited_items)):
        return ClaimVerification(
            claim_text=claim.text,
            status=CitationVerificationStatus.TEMPORAL_CONFLICT,
            citation_ids=claim.citation_ids,
            reason="claim date conflicts with cited evidence timestamp",
        )

    overlap = _support_overlap(claim.text, tuple(cited_items))
    if overlap < min_token_overlap:
        return ClaimVerification(
            claim_text=claim.text,
            status=CitationVerificationStatus.WEAK_SUPPORT,
            citation_ids=claim.citation_ids,
            reason=f"claim token overlap with cited evidence is too low: {overlap:.3f}",
        )

    return ClaimVerification(
        claim_text=claim.text,
        status=CitationVerificationStatus.SUPPORTED,
        citation_ids=claim.citation_ids,
        reason=f"citation exists and token overlap is {overlap:.3f}",
    )


def _support_overlap(claim_text: str, items: tuple[EvidenceItem, ...]) -> float:
    claim_tokens = _tokens(claim_text)
    if not claim_tokens:
        return 0.0
    evidence_tokens = set()
    for item in items:
        evidence_tokens.update(_tokens(item.text))
        if item.diff:
            evidence_tokens.update(_tokens(item.diff))
    return len(claim_tokens & evidence_tokens) / len(claim_tokens)


def _has_temporal_conflict(claim_text: str, items: tuple[EvidenceItem, ...]) -> bool:
    claim_years = {int(year) for year in re.findall(r"\b(20\d{2}|19\d{2})\b", claim_text)}
    if not claim_years:
        return False
    evidence_years = {item.occurred_at.year for item in items if item.occurred_at is not None}
    return bool(evidence_years and claim_years.isdisjoint(evidence_years))


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9_]+", text)}
