from __future__ import annotations

from datetime import datetime, timezone
import unittest

from git_archaeologist.chat.current_change_context import (
    CurrentChangeFetchError,
    CurrentChangeStatus,
    PullRequestLocator,
    PullRequestMetadata,
    build_current_change_context,
    parse_pr_url,
)


class CurrentChangeContextTests(unittest.TestCase):
    def test_parses_pr_url(self) -> None:
        locator = parse_pr_url("risk https://github.com/facebook/react/pull/12345")

        self.assertEqual("facebook/react", locator.repository)
        self.assertEqual(12345, locator.number)
        self.assertEqual("facebook/react#12345", locator.identifier)

    def test_fetches_metadata_diff_and_records_observation_point(self) -> None:
        fetched_at = datetime(2024, 2, 1, 12, 0, tzinfo=timezone.utc)
        context = build_current_change_context(
            "https://github.com/facebook/react/pull/12345",
            client=_SuccessfulClient(),
            index_version="index-2024-01-31",
            fetched_at=fetched_at,
        )

        self.assertEqual(CurrentChangeStatus.AVAILABLE, context.status)
        self.assertTrue(context.can_assess_current_change)
        self.assertEqual("head-sha", context.metadata.head_sha)
        self.assertIn("+new line", context.diff)
        self.assertEqual("index-2024-01-31", context.index_version)
        self.assertEqual("2024-02-01T12:00:00+00:00", context.to_dict()["fetched_at"])

    def test_fetch_failure_returns_safe_context_without_diff(self) -> None:
        context = build_current_change_context(
            "https://github.com/facebook/react/pull/12345",
            client=_FailingClient(),
            index_version="index-2024-01-31",
        )

        self.assertEqual(CurrentChangeStatus.FETCH_FAILED, context.status)
        self.assertFalse(context.can_assess_current_change)
        self.assertIsNone(context.metadata)
        self.assertIsNone(context.diff)
        self.assertIn("fetch failed", context.error or "")

    def test_invalid_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_current_change_context(
                "https://example.com/not-a-pr",
                client=_SuccessfulClient(),
                index_version="index",
            )


class _SuccessfulClient:
    def fetch_metadata(self, locator: PullRequestLocator) -> PullRequestMetadata:
        return PullRequestMetadata(
            repository=locator.repository,
            number=locator.number,
            title="Improve createRoot warnings",
            state="OPEN",
            head_sha="head-sha",
            base_sha="base-sha",
            html_url=locator.url,
        )

    def fetch_diff(self, locator: PullRequestLocator) -> str:
        return "@@ -1 +1 @@\n-old line\n+new line"


class _FailingClient:
    def fetch_metadata(self, locator: PullRequestLocator) -> PullRequestMetadata:
        raise CurrentChangeFetchError("network unavailable")

    def fetch_diff(self, locator: PullRequestLocator) -> str:
        raise AssertionError("diff should not be fetched after metadata failure")


if __name__ == "__main__":
    unittest.main()
