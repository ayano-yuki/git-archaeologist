"""Temporary context for PRs that are not yet indexed."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import re
from typing import Protocol


class CurrentChangeStatus(StrEnum):
    """Whether current PR metadata and diff are available."""

    AVAILABLE = "available"
    FETCH_FAILED = "fetch_failed"


@dataclass(frozen=True)
class PullRequestLocator:
    """Repository and PR number parsed from a GitHub PR URL."""

    repository: str
    number: int
    url: str

    @property
    def identifier(self) -> str:
        return f"{self.repository}#{self.number}"


@dataclass(frozen=True)
class PullRequestMetadata:
    """Minimum PR metadata needed for current-change risk checks."""

    repository: str
    number: int
    title: str
    state: str
    head_sha: str
    base_sha: str
    html_url: str

    def validate(self) -> None:
        for field_name in ("repository", "title", "state", "head_sha", "base_sha", "html_url"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be non-empty")
        if self.number < 1:
            raise ValueError("number must be positive")
        if not self.html_url.startswith(("https://", "http://")):
            raise ValueError("html_url must be an http or https URL")


@dataclass(frozen=True)
class CurrentChangeContext:
    """Ephemeral PR context used only for the current question."""

    status: CurrentChangeStatus
    locator: PullRequestLocator
    fetched_at: datetime
    index_version: str
    metadata: PullRequestMetadata | None = None
    diff: str | None = None
    error: str | None = None

    @property
    def can_assess_current_change(self) -> bool:
        return self.status is CurrentChangeStatus.AVAILABLE and self.metadata is not None and bool(self.diff)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "status": self.status.value,
            "locator": asdict(self.locator),
            "fetched_at": self.fetched_at.isoformat(),
            "index_version": self.index_version,
            "metadata": asdict(self.metadata) if self.metadata else None,
            "diff": self.diff,
            "error": self.error,
            "can_assess_current_change": self.can_assess_current_change,
        }
        return {key: value for key, value in payload.items() if value is not None}


class CurrentChangeClient(Protocol):
    """Client boundary for GitHub metadata and diff retrieval."""

    def fetch_metadata(self, locator: PullRequestLocator) -> PullRequestMetadata:
        """Fetch latest PR metadata."""

    def fetch_diff(self, locator: PullRequestLocator) -> str:
        """Fetch latest PR diff."""


class CurrentChangeFetchError(RuntimeError):
    """Raised when current PR context cannot be fetched safely."""


def build_current_change_context(
    pr_url: str,
    *,
    client: CurrentChangeClient,
    index_version: str,
    fetched_at: datetime | None = None,
) -> CurrentChangeContext:
    """Fetch metadata and diff for an unindexed PR without updating the index."""

    locator = parse_pr_url(pr_url)
    if locator is None:
        raise ValueError("pr_url must be a GitHub pull request URL")

    observed_at = fetched_at or datetime.now(timezone.utc)
    try:
        metadata = client.fetch_metadata(locator)
        metadata.validate()
        diff = client.fetch_diff(locator)
        if not diff.strip():
            raise CurrentChangeFetchError("PR diff was empty")
    except Exception as error:
        return CurrentChangeContext(
            status=CurrentChangeStatus.FETCH_FAILED,
            locator=locator,
            fetched_at=observed_at,
            index_version=index_version,
            error=f"current change fetch failed: {error}",
        )

    return CurrentChangeContext(
        status=CurrentChangeStatus.AVAILABLE,
        locator=locator,
        fetched_at=observed_at,
        index_version=index_version,
        metadata=metadata,
        diff=diff,
    )


def parse_pr_url(text: str) -> PullRequestLocator | None:
    """Parse a GitHub PR URL from user input."""

    match = re.search(r"https://github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)", text)
    if match is None:
        return None
    return PullRequestLocator(
        repository=match.group(1),
        number=int(match.group(2)),
        url=match.group(0),
    )
