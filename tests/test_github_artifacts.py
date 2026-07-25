from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import json
import unittest

from git_archaeologist.gh_access import GhCommandResult
from git_archaeologist.github_artifacts import (
    GithubCollectionOperation,
    build_child_github_artifact_requests,
    build_root_github_artifact_requests,
    collect_github_artifacts,
)
from git_archaeologist.repository_config import ArtifactKind, load_builtin_repository_config


class FakeGhRunner:
    def __init__(self, results: dict[tuple[str, ...], list[GhCommandResult]]) -> None:
        self._results = {key: list(value) for key, value in results.items()}
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: Sequence[str]) -> GhCommandResult:
        key = tuple(command)
        self.commands.append(key)
        try:
            results = self._results[key]
        except KeyError as exc:
            raise AssertionError(f"unexpected gh command: {key!r}") from exc
        if not results:
            raise AssertionError(f"no fake result remains for command: {key!r}")
        return results.pop(0)


class GithubArtifactCollectorTests(unittest.TestCase):
    def test_builds_root_requests_from_enabled_artifact_scopes(self) -> None:
        config = load_builtin_repository_config()

        requests = build_root_github_artifact_requests(config, limit=25)

        self.assertEqual(
            [
                GithubCollectionOperation.LIST_PULL_REQUESTS,
                GithubCollectionOperation.LIST_ISSUES,
                GithubCollectionOperation.LIST_WORKFLOW_RUNS,
            ],
            [request.operation for request in requests],
        )
        self.assertTrue(all("--repo" in request.command for request in requests))
        self.assertTrue(all("25" in request.command for request in requests))

    def test_collects_root_and_child_artifacts(self) -> None:
        config = load_builtin_repository_config()
        runner = FakeGhRunner(_success_results())

        report = collect_github_artifacts(
            config,
            runner=runner,
            fetched_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
            limit=1,
        )

        self.assertTrue(report.passed)
        self.assertEqual("react/react", report.repository_id)
        artifacts = {(artifact.artifact_kind, artifact.external_id) for artifact in report.artifacts}
        self.assertIn((ArtifactKind.PULL_REQUEST, "pull_request-123"), artifacts)
        self.assertIn((ArtifactKind.ISSUE, "issue-456"), artifacts)
        self.assertIn((ArtifactKind.REVIEW, "review-1001"), artifacts)
        self.assertIn((ArtifactKind.REVIEW_COMMENT, "review_comment-2001"), artifacts)
        self.assertIn((ArtifactKind.ISSUE_COMMENT, "issue_comment-3001"), artifacts)
        self.assertIn((ArtifactKind.CI_RUN, "ci_run-4001"), artifacts)
        self.assertIn((ArtifactKind.CI_JOB, "ci_job-5001"), artifacts)

    def test_builds_child_requests_from_root_artifacts(self) -> None:
        config = load_builtin_repository_config()
        report = collect_github_artifacts(
            config,
            runner=FakeGhRunner(_success_results()),
            fetched_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
            limit=1,
        )

        requests = build_child_github_artifact_requests(config, report.artifacts)

        operations = {request.operation for request in requests}
        self.assertIn(GithubCollectionOperation.LIST_PULL_REQUEST_REVIEWS, operations)
        self.assertIn(GithubCollectionOperation.LIST_PULL_REQUEST_REVIEW_COMMENTS, operations)
        self.assertIn(GithubCollectionOperation.LIST_ISSUE_COMMENTS, operations)
        self.assertIn(GithubCollectionOperation.LIST_WORKFLOW_RUN_JOBS, operations)

    def test_retries_retryable_failure_and_reports_human_payload(self) -> None:
        config = load_builtin_repository_config()
        results = _success_results()
        pr_command = (
            "gh",
            "pr",
            "list",
            "--repo",
            "react/react",
            "--state",
            "all",
            "--limit",
            "1",
            "--json",
            "number,state,title,body,author,createdAt,updatedAt,mergedAt,url,headRefName,baseRefName",
        )
        results[pr_command] = [
            GhCommandResult(returncode=1, stderr="rate limit exceeded"),
            GhCommandResult(returncode=0, stdout=_json([_pull_request()])),
        ]

        report = collect_github_artifacts(
            config,
            runner=FakeGhRunner(results),
            fetched_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
            limit=1,
            max_retries=1,
        )

        self.assertTrue(report.passed)

        blocked_results = _success_results()
        blocked_results[pr_command] = [
            GhCommandResult(returncode=1, stderr="rate limit exceeded"),
        ]
        blocked = collect_github_artifacts(
            config,
            runner=FakeGhRunner(blocked_results),
            fetched_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
            limit=1,
            max_retries=0,
        )

        self.assertFalse(blocked.passed)
        payload = blocked.human_payloads()[0]
        self.assertEqual("react/react", payload["repository_id"])
        self.assertEqual("pull_request", payload["artifact_kind"])
        self.assertEqual("rate_limit", payload["error_type"])
        self.assertEqual(0, payload["retry_count"])

    def test_rejects_naive_fetch_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "fetched_at must include a timezone"):
            collect_github_artifacts(
                load_builtin_repository_config(),
                runner=FakeGhRunner({}),
                fetched_at=datetime(2026, 7, 25),
            )


def _success_results() -> dict[tuple[str, ...], list[GhCommandResult]]:
    results = _root_only_results()
    results.update(
        {
            ("gh", "api", "repos/react/react/pulls/123/reviews?per_page=100"): [
                GhCommandResult(returncode=0, stdout=_json([_review()]))
            ],
            ("gh", "api", "repos/react/react/pulls/123/comments?per_page=100"): [
                GhCommandResult(returncode=0, stdout=_json([_review_comment()]))
            ],
            ("gh", "api", "repos/react/react/issues/123/comments?per_page=100"): [
                GhCommandResult(returncode=0, stdout=_json([_issue_comment(3001)]))
            ],
            ("gh", "api", "repos/react/react/issues/456/comments?per_page=100"): [
                GhCommandResult(returncode=0, stdout=_json([_issue_comment(3002)]))
            ],
            (
                "gh",
                "run",
                "view",
                "4001",
                "--repo",
                "react/react",
                "--json",
                "jobs",
            ): [GhCommandResult(returncode=0, stdout=_json({"jobs": [_ci_job()]}))],
        }
    )
    return results


def _root_only_results() -> dict[tuple[str, ...], list[GhCommandResult]]:
    return {
        (
            "gh",
            "pr",
            "list",
            "--repo",
            "react/react",
            "--state",
            "all",
            "--limit",
            "1",
            "--json",
            "number,state,title,body,author,createdAt,updatedAt,mergedAt,url,headRefName,baseRefName",
        ): [GhCommandResult(returncode=0, stdout=_json([_pull_request()]))],
        (
            "gh",
            "issue",
            "list",
            "--repo",
            "react/react",
            "--state",
            "all",
            "--limit",
            "1",
            "--json",
            "number,state,title,body,author,createdAt,updatedAt,url",
        ): [GhCommandResult(returncode=0, stdout=_json([_issue()]))],
        (
            "gh",
            "run",
            "list",
            "--repo",
            "react/react",
            "--limit",
            "1",
            "--json",
            "databaseId,displayTitle,status,conclusion,workflowName,headSha,event,createdAt,updatedAt,url",
        ): [GhCommandResult(returncode=0, stdout=_json([_ci_run()]))],
    }


def _pull_request() -> dict[str, object]:
    return {
        "number": 123,
        "state": "MERGED",
        "title": "Fix scheduler regression",
        "url": "https://github.com/react/react/pull/123",
    }


def _issue() -> dict[str, object]:
    return {
        "number": 456,
        "state": "CLOSED",
        "title": "Scheduler regression",
        "url": "https://github.com/react/react/issues/456",
    }


def _review() -> dict[str, object]:
    return {
        "id": 1001,
        "state": "APPROVED",
        "body": "Looks good.",
        "html_url": "https://github.com/react/react/pull/123#pullrequestreview-1001",
    }


def _review_comment() -> dict[str, object]:
    return {
        "id": 2001,
        "body": "Please keep this guard.",
        "html_url": "https://github.com/react/react/pull/123#discussion_r2001",
    }


def _issue_comment(comment_id: int) -> dict[str, object]:
    return {
        "id": comment_id,
        "body": "Issue comment.",
        "html_url": f"https://github.com/react/react/issues/456#issuecomment-{comment_id}",
    }


def _ci_run() -> dict[str, object]:
    return {
        "databaseId": 4001,
        "status": "completed",
        "conclusion": "success",
        "url": "https://github.com/react/react/actions/runs/4001",
    }


def _ci_job() -> dict[str, object]:
    return {
        "databaseId": 5001,
        "name": "test",
        "conclusion": "success",
        "url": "https://github.com/react/react/actions/runs/4001/job/5001",
    }


def _json(value: object) -> str:
    return json.dumps(value)


if __name__ == "__main__":
    unittest.main()
