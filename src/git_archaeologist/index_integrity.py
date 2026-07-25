"""Index version transactions for keeping storage generations aligned."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IndexTransactionStatus(StrEnum):
    """Lifecycle state of an index update transaction."""

    STAGED = "staged"
    PUBLISHED = "published"
    ABORTED = "aborted"


@dataclass(frozen=True)
class IndexGeneration:
    """Version set for all stores required by an answer."""

    raw_archive_version: str
    event_version: str
    embedding_version: str
    graph_version: str
    synced_at: str

    @property
    def is_consistent(self) -> bool:
        versions = {
            self.raw_archive_version,
            self.event_version,
            self.embedding_version,
            self.graph_version,
        }
        return len(versions) == 1

    @property
    def index_version(self) -> str:
        if not self.is_consistent:
            raise ValueError("index generations are not aligned")
        return self.raw_archive_version


@dataclass(frozen=True)
class IndexTransaction:
    """Atomic publish guard for a newly built index generation."""

    base_index_version: str
    staged_index_version: str
    status: IndexTransactionStatus = IndexTransactionStatus.STAGED

    def publish(self, generation: IndexGeneration) -> "IndexTransaction":
        if self.status is not IndexTransactionStatus.STAGED:
            raise ValueError("only staged transactions can be published")
        if not generation.is_consistent:
            raise ValueError("cannot publish inconsistent index generation")
        if generation.index_version != self.staged_index_version:
            raise ValueError("generation version does not match staged transaction")
        return IndexTransaction(
            base_index_version=self.base_index_version,
            staged_index_version=self.staged_index_version,
            status=IndexTransactionStatus.PUBLISHED,
        )

    def abort(self) -> "IndexTransaction":
        return IndexTransaction(
            base_index_version=self.base_index_version,
            staged_index_version=self.staged_index_version,
            status=IndexTransactionStatus.ABORTED,
        )


@dataclass(frozen=True)
class AnswerIndexReference:
    """Index metadata attached to a generated answer."""

    index_version: str
    synced_at: str


def ensure_answer_uses_published_index(
    generation: IndexGeneration,
    transaction: IndexTransaction,
) -> AnswerIndexReference:
    """Return answer metadata only for a fully published, aligned generation."""

    if transaction.status is not IndexTransactionStatus.PUBLISHED:
        raise ValueError("answers cannot use unpublished index generations")
    if generation.index_version != transaction.staged_index_version:
        raise ValueError("answer generation mismatch")
    return AnswerIndexReference(index_version=generation.index_version, synced_at=generation.synced_at)
