"""Keyword, vector, filter, and rank-fusion search contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import re
from typing import Protocol


class SearchSource(StrEnum):
    """Source that produced a search hit."""

    KEYWORD = "keyword"
    VECTOR = "vector"
    FUSION = "fusion"


@dataclass(frozen=True)
class SearchDocument:
    """One searchable unit from an indexed artifact or code chunk."""

    document_id: str
    text: str
    file_path: str | None = None
    symbol_id: str | None = None
    artifact_kind: str | None = None
    timestamp: datetime | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        for field_name in ("document_id", "text"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be non-empty")


@dataclass(frozen=True)
class SearchFilter:
    """Structured filters applied consistently across search backends."""

    file_path: str | None = None
    symbol_id: str | None = None
    artifact_kind: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    def matches(self, document: SearchDocument) -> bool:
        if self.file_path and document.file_path != self.file_path:
            return False
        if self.symbol_id and document.symbol_id != self.symbol_id:
            return False
        if self.artifact_kind and document.artifact_kind != self.artifact_kind:
            return False
        if self.start_time and (document.timestamp is None or document.timestamp < self.start_time):
            return False
        if self.end_time and (document.timestamp is None or document.timestamp > self.end_time):
            return False
        return True


@dataclass(frozen=True)
class SearchHit:
    """Ranked search hit with an inspectable explanation."""

    document: SearchDocument
    score: float
    source: SearchSource
    explanation: str
    matched_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = {
            "document_id": self.document.document_id,
            "score": self.score,
            "source": self.source.value,
            "explanation": self.explanation,
            "matched_terms": list(self.matched_terms),
            "file_path": self.document.file_path,
            "symbol_id": self.document.symbol_id,
            "artifact_kind": self.document.artifact_kind,
        }
        return {key: value for key, value in payload.items() if value is not None}


class VectorSearchBackend(Protocol):
    """Backend boundary for replaceable embedding/vector search implementations."""

    def search(
        self,
        query: str,
        documents: tuple[SearchDocument, ...],
        *,
        search_filter: SearchFilter | None = None,
        limit: int = 10,
    ) -> tuple[SearchHit, ...]:
        """Return vector-ranked hits for the supplied query."""


@dataclass(frozen=True)
class DeterministicVectorSearchBackend:
    """Deterministic vector backend for tests and early local evaluation."""

    scores_by_document_id: Mapping[str, float]

    def search(
        self,
        query: str,
        documents: tuple[SearchDocument, ...],
        *,
        search_filter: SearchFilter | None = None,
        limit: int = 10,
    ) -> tuple[SearchHit, ...]:
        hits = [
            SearchHit(
                document=document,
                score=score,
                source=SearchSource.VECTOR,
                explanation=f"deterministic vector score for query '{query}'",
            )
            for document in _filtered(documents, search_filter)
            if (score := self.scores_by_document_id.get(document.document_id, 0.0)) > 0
        ]
        return tuple(sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit])


@dataclass(frozen=True)
class KeywordSearchEngine:
    """Small deterministic keyword search used until persistent FTS is wired in."""

    documents: tuple[SearchDocument, ...]

    def search(
        self,
        query: str,
        *,
        search_filter: SearchFilter | None = None,
        limit: int = 10,
    ) -> tuple[SearchHit, ...]:
        query_terms = _tokens(query)
        if not query_terms:
            return ()

        hits: list[SearchHit] = []
        for document in _filtered(self.documents, search_filter):
            document.validate()
            document_terms = _tokens(document.text)
            matched = tuple(sorted(query_terms & document_terms))
            if not matched:
                continue

            phrase_boost = 1.0 if query.lower() in document.text.lower() else 0.0
            identifier_boost = 0.5 if any(term in _identifier_terms(document) for term in query_terms) else 0.0
            score = len(matched) / len(query_terms) + phrase_boost + identifier_boost
            hits.append(
                SearchHit(
                    document=document,
                    score=round(score, 4),
                    source=SearchSource.KEYWORD,
                    explanation="matched query terms with exact identifier and phrase boosts",
                    matched_terms=matched,
                )
            )
        return tuple(sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit])


@dataclass(frozen=True)
class HybridSearchEngine:
    """Combine keyword and vector results with reciprocal-rank fusion."""

    documents: tuple[SearchDocument, ...]
    vector_backend: VectorSearchBackend

    def search(
        self,
        query: str,
        *,
        search_filter: SearchFilter | None = None,
        limit: int = 10,
    ) -> tuple[SearchHit, ...]:
        keyword_hits = KeywordSearchEngine(self.documents).search(
            query,
            search_filter=search_filter,
            limit=limit,
        )
        vector_hits = self.vector_backend.search(
            query,
            self.documents,
            search_filter=search_filter,
            limit=limit,
        )
        return reciprocal_rank_fusion(keyword_hits, vector_hits, limit=limit)


def reciprocal_rank_fusion(
    keyword_hits: Iterable[SearchHit],
    vector_hits: Iterable[SearchHit],
    *,
    limit: int = 10,
    rank_constant: int = 60,
) -> tuple[SearchHit, ...]:
    """Fuse keyword and vector rankings while preserving explainability."""

    score_by_id: dict[str, float] = {}
    document_by_id: dict[str, SearchDocument] = {}
    reasons_by_id: dict[str, list[str]] = {}
    terms_by_id: dict[str, set[str]] = {}

    for label, hits in (("keyword", tuple(keyword_hits)), ("vector", tuple(vector_hits))):
        for rank, hit in enumerate(hits, start=1):
            document_id = hit.document.document_id
            score_by_id[document_id] = score_by_id.get(document_id, 0.0) + 1 / (rank_constant + rank)
            document_by_id[document_id] = hit.document
            reasons_by_id.setdefault(document_id, []).append(f"{label} rank {rank}")
            terms_by_id.setdefault(document_id, set()).update(hit.matched_terms)

    fused = [
        SearchHit(
            document=document_by_id[document_id],
            score=round(score, 6),
            source=SearchSource.FUSION,
            explanation="; ".join(reasons_by_id[document_id]),
            matched_terms=tuple(sorted(terms_by_id[document_id])),
        )
        for document_id, score in score_by_id.items()
    ]
    return tuple(sorted(fused, key=lambda hit: hit.score, reverse=True)[:limit])


def _filtered(
    documents: tuple[SearchDocument, ...],
    search_filter: SearchFilter | None,
) -> tuple[SearchDocument, ...]:
    if search_filter is None:
        return documents
    return tuple(document for document in documents if search_filter.matches(document))


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9_./:-]+", text)}


def _identifier_terms(document: SearchDocument) -> set[str]:
    terms = set()
    for value in (document.file_path, document.symbol_id, document.artifact_kind):
        if value:
            terms.update(_tokens(value))
    return terms
