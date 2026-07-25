from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import unittest

from git_archaeologist.gh_access import (
    GhCheckKind,
    GhCommandResult,
    GhErrorType,
    check_github_access,
    classify_gh_error,
)
from git_archaeologist.repository_config import load_builtin_repository_config


FIXTURES = Path(__file__).parent / "fixtures" / "gh"


class FakeGhRunner:
    def __init__(self, results: dict[tuple[str, ...], GhCommandResult]) -> None:
        self._results = results
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: Sequence[str]) -> GhCommandResult:
        key = tuple(command)
        self.commands.append(key)
        try:
            return self._results[key]
        except KeyError as exc:
            raise AssertionError(f"unexpected gh command: {key!r}") from exc


class GhAccessTests(unittest.TestCase):
    def test_checks_react_read_access_before_collection(self) -> None:
        runner = FakeGhRunner(_success_results())

        report = check_github_access(load_builtin_repository_config(), runner)

        self.assertTrue(report.passed)
        self.assertEqual(
            [check.kind for check in report.checks],
            [
                GhCheckKind.AUTHENTICATION,
                GhCheckKind.REPOSITORY,
                GhCheckKind.PULL_REQUEST,
                GhCheckKind.ISSUE,
                GhCheckKind.ACTIONS,
                GhCheckKind.REVIEW,
            ],
        )
        self.assertIn(
            (
                "gh",
                "api",
                "repos/react/react/pulls/123/reviews?per_page=1",
            ),
            runner.commands,
        )

    def test_stops_after_authentication_failure(self) -> None:
        runner = FakeGhRunner(
            {
                ("gh", "auth", "status"): GhCommandResult(
                    returncode=1,
                    stderr=_fixture("auth_status_not_logged_in.txt"),
                )
            }
        )

        report = check_github_access(load_builtin_repository_config(), runner)

        self.assertFalse(report.passed)
        self.assertEqual(len(report.checks), 1)
        failure = report.failures[0]
        self.assertEqual(failure.error_type, GhErrorType.AUTHENTICATION)
        self.assertFalse(failure.retryable)
        self.assertEqual(
            failure.human_payload("react/react"),
            {
                "repository_id": "react/react",
                "target": "react/react",
                "operation": "gh auth status",
                "error_type": "authentication",
                "cause": "gh CLI is not authenticated for GitHub.",
                "retryable": False,
            },
        )

    def test_classifies_actions_permission_failure(self) -> None:
        results = _success_results()
        results[
            (
                "gh",
                "run",
                "list",
                "--repo",
                "react/react",
                "--limit",
                "1",
                "--json",
                "databaseId,status,conclusion,workflowName",
            )
        ] = GhCommandResult(returncode=1, stderr=_fixture("actions_forbidden.txt"))

        report = check_github_access(load_builtin_repository_config(), FakeGhRunner(results))

        self.assertFalse(report.passed)
        failure = _failure_for(report, GhCheckKind.ACTIONS)
        self.assertEqual(failure.error_type, GhErrorType.INSUFFICIENT_PERMISSIONS)
        self.assertFalse(failure.retryable)

    def test_classifies_proxy_and_network_failure_as_retryable(self) -> None:
        classified = classify_gh_error(
            GhCommandResult(returncode=1, stderr=_fixture("proxy_failure.txt"))
        )

        self.assertEqual(classified, GhErrorType.PROXY)

        results = _success_results()
        results[
            (
                "gh",
                "repo",
                "view",
                "react/react",
                "--json",
                "nameWithOwner,visibility,defaultBranchRef",
            )
        ] = GhCommandResult(returncode=1, stderr=_fixture("proxy_failure.txt"))

        report = check_github_access(load_builtin_repository_config(), FakeGhRunner(results))
        failure = _failure_for(report, GhCheckKind.REPOSITORY)
        self.assertEqual(failure.error_type, GhErrorType.PROXY)
        self.assertTrue(failure.retryable)

        network_classified = classify_gh_error(
            GhCommandResult(returncode=1, stderr=_fixture("network_failure.txt"))
        )
        self.assertEqual(network_classified, GhErrorType.NETWORK)

    def test_classifies_certificate_failure_as_retryable(self) -> None:
        classified = classify_gh_error(
            GhCommandResult(returncode=1, stderr=_fixture("certificate_failure.txt"))
        )

        self.assertEqual(classified, GhErrorType.TLS_CERTIFICATE)

    def test_classifies_rate_limit_as_retryable(self) -> None:
        classified = classify_gh_error(
            GhCommandResult(returncode=1, stderr=_fixture("rate_limit_failure.txt"))
        )

        self.assertEqual(classified, GhErrorType.RATE_LIMIT)

    def test_reports_invalid_review_target_response(self) -> None:
        results = _success_results()
        results[("gh", "api", "repos/react/react/pulls?state=all&per_page=1")] = (
            GhCommandResult(returncode=0, stdout="[]")
        )

        report = check_github_access(load_builtin_repository_config(), FakeGhRunner(results))

        self.assertFalse(report.passed)
        failure = _failure_for(report, GhCheckKind.REVIEW)
        self.assertEqual(failure.error_type, GhErrorType.INVALID_RESPONSE)
        self.assertEqual(failure.target, "react/react")


def _success_results() -> dict[tuple[str, ...], GhCommandResult]:
    return {
        ("gh", "auth", "status"): GhCommandResult(
            returncode=0,
            stdout=_fixture("auth_status_success.txt"),
        ),
        (
            "gh",
            "repo",
            "view",
            "react/react",
            "--json",
            "nameWithOwner,visibility,defaultBranchRef",
        ): GhCommandResult(returncode=0, stdout=_fixture("repo_view_success.json")),
        (
            "gh",
            "pr",
            "list",
            "--repo",
            "react/react",
            "--limit",
            "1",
            "--json",
            "number,state,updatedAt",
        ): GhCommandResult(returncode=0, stdout=_fixture("pr_list_success.json")),
        (
            "gh",
            "issue",
            "list",
            "--repo",
            "react/react",
            "--limit",
            "1",
            "--json",
            "number,state,updatedAt",
        ): GhCommandResult(returncode=0, stdout=_fixture("issue_list_success.json")),
        (
            "gh",
            "api",
            "repos/react/react/pulls?state=all&per_page=1",
        ): GhCommandResult(returncode=0, stdout=_fixture("pulls_success.json")),
        (
            "gh",
            "api",
            "repos/react/react/pulls/123/reviews?per_page=1",
        ): GhCommandResult(returncode=0, stdout=_fixture("reviews_success.json")),
        (
            "gh",
            "run",
            "list",
            "--repo",
            "react/react",
            "--limit",
            "1",
            "--json",
            "databaseId,status,conclusion,workflowName",
        ): GhCommandResult(returncode=0, stdout=_fixture("run_list_success.json")),
    }


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _failure_for(report, kind: GhCheckKind):
    for failure in report.failures:
        if failure.check == kind:
            return failure
    raise AssertionError(f"missing failure for {kind}")


if __name__ == "__main__":
    unittest.main()
