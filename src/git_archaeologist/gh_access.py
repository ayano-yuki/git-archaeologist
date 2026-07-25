"""Preflight checks for GitHub access through the gh CLI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
import json
import subprocess
from typing import Protocol

from git_archaeologist.repository_config import ArtifactKind, RepositoryConfig


class GhCheckKind(str, Enum):
    """GitHub access checks required before collection starts."""

    AUTHENTICATION = "authentication"
    REPOSITORY = "repository"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    REVIEW = "review"
    ACTIONS = "actions"


class GhErrorType(str, Enum):
    """Human-facing failure categories for gh/GitHub access."""

    AUTHENTICATION = "authentication"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    NETWORK = "network"
    PROXY = "proxy"
    TLS_CERTIFICATE = "tls_certificate"
    RATE_LIMIT = "rate_limit"
    REPOSITORY_UNAVAILABLE = "repository_unavailable"
    GH_CLI_UNAVAILABLE = "gh_cli_unavailable"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GhCommandResult:
    """Completed gh command result."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def output(self) -> str:
        return "\n".join(part for part in (self.stdout, self.stderr) if part)


class GhRunner(Protocol):
    """Callable gh command runner."""

    def __call__(self, command: Sequence[str]) -> GhCommandResult:
        """Run a gh command and return captured output."""


@dataclass(frozen=True)
class GhFailure:
    """Classified access failure suitable for human escalation."""

    check: GhCheckKind
    target: str
    operation: str
    error_type: GhErrorType
    cause: str
    retryable: bool
    command: tuple[str, ...]
    raw_output: str

    def human_payload(self, repository_id: str) -> dict[str, object]:
        """Return the minimal payload a human needs to diagnose the failure."""

        return {
            "repository_id": repository_id,
            "target": self.target,
            "operation": self.operation,
            "error_type": self.error_type.value,
            "cause": self.cause,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class GhCheckResult:
    """Result for one preflight check."""

    kind: GhCheckKind
    target: str
    operation: str
    passed: bool
    failure: GhFailure | None = None


@dataclass(frozen=True)
class GhPreflightReport:
    """Aggregate GitHub access preflight report."""

    repository_id: str
    checks: tuple[GhCheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[GhFailure, ...]:
        return tuple(
            check.failure for check in self.checks if check.failure is not None
        )

    def human_payloads(self) -> tuple[dict[str, object], ...]:
        """Return classified failures for notifying a human operator."""

        return tuple(
            failure.human_payload(self.repository_id) for failure in self.failures
        )


@dataclass(frozen=True)
class _CheckSpec:
    kind: GhCheckKind
    target: str
    operation: str
    command: tuple[str, ...]


def run_gh_command(command: Sequence[str]) -> GhCommandResult:
    """Run a gh command with stdout/stderr captured."""

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        return GhCommandResult(returncode=127, stderr=str(exc))

    return GhCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def check_github_access(
    config: RepositoryConfig,
    runner: GhRunner = run_gh_command,
) -> GhPreflightReport:
    """Check gh auth and read access needed by enabled repository artifacts."""

    checks: list[GhCheckResult] = []
    auth_spec = _CheckSpec(
        kind=GhCheckKind.AUTHENTICATION,
        target=config.repository_id,
        operation="gh auth status",
        command=("gh", "auth", "status"),
    )
    checks.append(_run_check(auth_spec, runner))
    if not checks[-1].passed:
        return GhPreflightReport(repository_id=config.repository_id, checks=tuple(checks))

    for spec in _build_static_check_specs(config):
        checks.append(_run_check(spec, runner))

    if _requires_review_check(config):
        checks.append(_run_review_check(config, runner))

    return GhPreflightReport(repository_id=config.repository_id, checks=tuple(checks))


def _build_static_check_specs(config: RepositoryConfig) -> tuple[_CheckSpec, ...]:
    repository = config.repository_id
    specs = [
        _CheckSpec(
            kind=GhCheckKind.REPOSITORY,
            target=repository,
            operation="read repository metadata",
            command=(
                "gh",
                "repo",
                "view",
                repository,
                "--json",
                "nameWithOwner,visibility,defaultBranchRef",
            ),
        )
    ]

    enabled = set(config.enabled_artifact_kinds)
    if ArtifactKind.PULL_REQUEST in enabled:
        specs.append(
            _CheckSpec(
                kind=GhCheckKind.PULL_REQUEST,
                target=repository,
                operation="list pull requests",
                command=(
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    repository,
                    "--limit",
                    "1",
                    "--json",
                    "number,state,updatedAt",
                ),
            )
        )
    if ArtifactKind.ISSUE in enabled:
        specs.append(
            _CheckSpec(
                kind=GhCheckKind.ISSUE,
                target=repository,
                operation="list issues",
                command=(
                    "gh",
                    "issue",
                    "list",
                    "--repo",
                    repository,
                    "--limit",
                    "1",
                    "--json",
                    "number,state,updatedAt",
                ),
            )
        )
    if ArtifactKind.CI_RUN in enabled or ArtifactKind.CI_JOB in enabled:
        specs.append(
            _CheckSpec(
                kind=GhCheckKind.ACTIONS,
                target=repository,
                operation="list workflow runs",
                command=(
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    repository,
                    "--limit",
                    "1",
                    "--json",
                    "databaseId,status,conclusion,workflowName",
                ),
            )
        )

    return tuple(specs)


def _requires_review_check(config: RepositoryConfig) -> bool:
    enabled = set(config.enabled_artifact_kinds)
    return bool({ArtifactKind.REVIEW, ArtifactKind.REVIEW_COMMENT} & enabled)


def _run_review_check(
    config: RepositoryConfig,
    runner: GhRunner,
) -> GhCheckResult:
    repository = config.repository_id
    pulls_spec = _CheckSpec(
        kind=GhCheckKind.REVIEW,
        target=repository,
        operation="find pull request for review access check",
        command=("gh", "api", f"repos/{repository}/pulls?state=all&per_page=1"),
    )
    pulls_result = runner(pulls_spec.command)
    if pulls_result.returncode != 0:
        return _failure_result(pulls_spec, pulls_result)

    pull_number = _parse_first_pull_number(pulls_result.stdout)
    if pull_number is None:
        result = GhCommandResult(
            returncode=1,
            stderr="No pull request was returned for review access check.",
        )
        return _failure_result(pulls_spec, result, error_type=GhErrorType.INVALID_RESPONSE)

    reviews_spec = _CheckSpec(
        kind=GhCheckKind.REVIEW,
        target=f"{repository}#{pull_number}",
        operation="list pull request reviews",
        command=(
            "gh",
            "api",
            f"repos/{repository}/pulls/{pull_number}/reviews?per_page=1",
        ),
    )
    return _run_check(reviews_spec, runner)


def _parse_first_pull_number(output: str) -> int | None:
    try:
        parsed = json.loads(output or "[]")
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, list) or not parsed:
        return None
    first = parsed[0]
    if not isinstance(first, dict):
        return None
    number = first.get("number")
    if not isinstance(number, int):
        return None
    return number


def _run_check(spec: _CheckSpec, runner: GhRunner) -> GhCheckResult:
    result = runner(spec.command)
    if result.returncode == 0:
        return GhCheckResult(
            kind=spec.kind,
            target=spec.target,
            operation=spec.operation,
            passed=True,
        )
    return _failure_result(spec, result)


def _failure_result(
    spec: _CheckSpec,
    result: GhCommandResult,
    error_type: GhErrorType | None = None,
) -> GhCheckResult:
    classified_type = error_type or classify_gh_error(result)
    failure = GhFailure(
        check=spec.kind,
        target=spec.target,
        operation=spec.operation,
        error_type=classified_type,
        cause=_cause_for_error(classified_type),
        retryable=_is_retryable(classified_type),
        command=spec.command,
        raw_output=result.output,
    )
    return GhCheckResult(
        kind=spec.kind,
        target=spec.target,
        operation=spec.operation,
        passed=False,
        failure=failure,
    )


def classify_gh_error(result: GhCommandResult) -> GhErrorType:
    """Classify gh stderr/stdout into stable operator-facing categories."""

    if result.returncode == 127:
        return GhErrorType.GH_CLI_UNAVAILABLE

    output = result.output.lower()
    if _contains_any(output, ("rate limit", "secondary rate", "http 429")):
        return GhErrorType.RATE_LIMIT
    if _contains_any(
        output,
        (
            "x509",
            "certificate",
            "ssl certificate",
            "schannel",
            "local issuer",
            "tls handshake",
        ),
    ):
        return GhErrorType.TLS_CERTIFICATE
    if _contains_any(
        output,
        (
            "proxyconnect",
            "proxy error",
            "proxy authentication",
            "407 proxy",
            "407 authenticationrequired",
        ),
    ):
        return GhErrorType.PROXY
    if _contains_any(
        output,
        (
            "could not resolve host",
            "connection refused",
            "connection reset",
            "connection timed out",
            "i/o timeout",
            "lookup ",
            "network is unreachable",
            "no such host",
            "no route to host",
        ),
    ):
        return GhErrorType.NETWORK
    if _contains_any(
        output,
        (
            "not logged into",
            "not logged in",
            "authentication required",
            "requires authentication",
            "bad credentials",
            "no oauth token",
            "gh auth login",
            "http 401",
        ),
    ):
        return GhErrorType.AUTHENTICATION
    if _contains_any(
        output,
        (
            "insufficient",
            "resource not accessible",
            "permission denied",
            "forbidden",
            "http 403",
        ),
    ):
        return GhErrorType.INSUFFICIENT_PERMISSIONS
    if _contains_any(output, ("not found", "http 404", "could not resolve to")):
        return GhErrorType.REPOSITORY_UNAVAILABLE
    return GhErrorType.UNKNOWN


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _is_retryable(error_type: GhErrorType) -> bool:
    return error_type in {
        GhErrorType.NETWORK,
        GhErrorType.PROXY,
        GhErrorType.TLS_CERTIFICATE,
        GhErrorType.RATE_LIMIT,
        GhErrorType.UNKNOWN,
    }


def _cause_for_error(error_type: GhErrorType) -> str:
    causes = {
        GhErrorType.AUTHENTICATION: "gh CLI is not authenticated for GitHub.",
        GhErrorType.INSUFFICIENT_PERMISSIONS: (
            "The authenticated GitHub identity lacks required read permission."
        ),
        GhErrorType.NETWORK: "GitHub could not be reached over the network.",
        GhErrorType.PROXY: "GitHub access failed through the configured proxy.",
        GhErrorType.TLS_CERTIFICATE: (
            "GitHub TLS certificate validation failed in this environment."
        ),
        GhErrorType.RATE_LIMIT: "GitHub API rate limit was reached.",
        GhErrorType.REPOSITORY_UNAVAILABLE: (
            "The repository was not found or is hidden from the current identity."
        ),
        GhErrorType.GH_CLI_UNAVAILABLE: "The gh CLI executable was not found.",
        GhErrorType.INVALID_RESPONSE: "GitHub returned an unexpected response shape.",
        GhErrorType.UNKNOWN: "gh failed for an unclassified reason.",
    }
    return causes[error_type]
