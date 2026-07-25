"""GitHub artifact collection through the gh CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from typing import Any

from git_archaeologist.collectors.gh_access import (
    GhCommandResult,
    GhErrorType,
    GhFailure,
    GhRunner,
    classify_gh_error,
    run_gh_command,
)
from git_archaeologist.config.repository_config import ArtifactKind, RepositoryConfig


DEFAULT_LIST_LIMIT = 100


class GithubCollectionOperation(StrEnum):
    """gh operations used by the GitHub Artifact Collector."""

    LIST_PULL_REQUESTS = "list_pull_requests"
    LIST_ISSUES = "list_issues"
    LIST_WORKFLOW_RUNS = "list_workflow_runs"
    LIST_PULL_REQUEST_REVIEWS = "list_pull_request_reviews"
    LIST_PULL_REQUEST_REVIEW_COMMENTS = "list_pull_request_review_comments"
    LIST_ISSUE_COMMENTS = "list_issue_comments"
    LIST_WORKFLOW_RUN_JOBS = "list_workflow_run_jobs"


@dataclass(frozen=True)
class GithubArtifactRequest:
    """One gh command needed to collect an artifact page or child artifact."""

    operation: GithubCollectionOperation
    artifact_kind: ArtifactKind
    target: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class CollectedGithubArtifact:
    """Raw GitHub artifact returned by gh before Raw Archive storage."""

    artifact_kind: ArtifactKind
    external_id: str
    source_url: str
    fetched_at: str
    raw: dict[str, Any]
    request: GithubArtifactRequest


@dataclass(frozen=True)
class GithubCollectionFailure:
    """Collection failure suitable for human escalation."""

    request: GithubArtifactRequest
    error_type: GhErrorType
    error_message: str
    retryable: bool
    retry_count: int

    def human_payload(self, repository_id: str) -> dict[str, object]:
        """Return the fields required by RepositoryConfig.error_reporting."""

        return {
            "repository_id": repository_id,
            "artifact_kind": self.request.artifact_kind.value,
            "target": self.request.target,
            "operation": self.request.operation.value,
            "error_type": self.error_type.value,
            "error_message": self.error_message,
            "source_url": _source_url_from_target(repository_id, self.request.target),
            "retry_count": self.retry_count,
        }


@dataclass(frozen=True)
class GithubCollectionReport:
    """Collected artifacts and failures from one collection run."""

    repository_id: str
    fetched_at: str
    artifacts: tuple[CollectedGithubArtifact, ...]
    failures: tuple[GithubCollectionFailure, ...]

    @property
    def passed(self) -> bool:
        return not self.failures

    def human_payloads(self) -> tuple[dict[str, object], ...]:
        """Return human-facing failure payloads."""

        return tuple(
            failure.human_payload(self.repository_id) for failure in self.failures
        )


def build_root_github_artifact_requests(
    config: RepositoryConfig,
    *,
    limit: int = DEFAULT_LIST_LIMIT,
) -> tuple[GithubArtifactRequest, ...]:
    """Build top-level list requests from enabled repository artifact scopes."""

    if limit <= 0:
        raise ValueError("limit must be positive")

    repository = config.repository_id
    enabled = set(config.enabled_artifact_kinds)
    requests: list[GithubArtifactRequest] = []

    if ArtifactKind.PULL_REQUEST in enabled:
        requests.append(
            GithubArtifactRequest(
                operation=GithubCollectionOperation.LIST_PULL_REQUESTS,
                artifact_kind=ArtifactKind.PULL_REQUEST,
                target=repository,
                command=(
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    repository,
                    "--state",
                    "all",
                    "--limit",
                    str(limit),
                    "--json",
                    "number,state,title,body,author,createdAt,updatedAt,mergedAt,url,headRefName,baseRefName",
                ),
            )
        )

    if ArtifactKind.ISSUE in enabled:
        requests.append(
            GithubArtifactRequest(
                operation=GithubCollectionOperation.LIST_ISSUES,
                artifact_kind=ArtifactKind.ISSUE,
                target=repository,
                command=(
                    "gh",
                    "issue",
                    "list",
                    "--repo",
                    repository,
                    "--state",
                    "all",
                    "--limit",
                    str(limit),
                    "--json",
                    "number,state,title,body,author,createdAt,updatedAt,url",
                ),
            )
        )

    if ArtifactKind.CI_RUN in enabled:
        requests.append(
            GithubArtifactRequest(
                operation=GithubCollectionOperation.LIST_WORKFLOW_RUNS,
                artifact_kind=ArtifactKind.CI_RUN,
                target=repository,
                command=(
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    repository,
                    "--limit",
                    str(limit),
                    "--json",
                    "databaseId,displayTitle,status,conclusion,workflowName,headSha,event,createdAt,updatedAt,url",
                ),
            )
        )

    return tuple(requests)


def build_child_github_artifact_requests(
    config: RepositoryConfig,
    root_artifacts: tuple[CollectedGithubArtifact, ...],
) -> tuple[GithubArtifactRequest, ...]:
    """Build review, comment, and CI job requests from collected root artifacts."""

    repository = config.repository_id
    enabled = set(config.enabled_artifact_kinds)
    requests: list[GithubArtifactRequest] = []

    for artifact in root_artifacts:
        if artifact.artifact_kind == ArtifactKind.PULL_REQUEST:
            number = _require_int_field(artifact.raw, "number")
            if ArtifactKind.REVIEW in enabled:
                requests.append(
                    GithubArtifactRequest(
                        operation=GithubCollectionOperation.LIST_PULL_REQUEST_REVIEWS,
                        artifact_kind=ArtifactKind.REVIEW,
                        target=f"{repository}#{number}",
                        command=(
                            "gh",
                            "api",
                            f"repos/{repository}/pulls/{number}/reviews?per_page=100",
                        ),
                    )
                )
            if ArtifactKind.REVIEW_COMMENT in enabled:
                requests.append(
                    GithubArtifactRequest(
                        operation=GithubCollectionOperation.LIST_PULL_REQUEST_REVIEW_COMMENTS,
                        artifact_kind=ArtifactKind.REVIEW_COMMENT,
                        target=f"{repository}#{number}",
                        command=(
                            "gh",
                            "api",
                            f"repos/{repository}/pulls/{number}/comments?per_page=100",
                        ),
                    )
                )
            if ArtifactKind.ISSUE_COMMENT in enabled:
                requests.append(
                    GithubArtifactRequest(
                        operation=GithubCollectionOperation.LIST_ISSUE_COMMENTS,
                        artifact_kind=ArtifactKind.ISSUE_COMMENT,
                        target=f"{repository}#{number}",
                        command=(
                            "gh",
                            "api",
                            f"repos/{repository}/issues/{number}/comments?per_page=100",
                        ),
                    )
                )

        if artifact.artifact_kind == ArtifactKind.ISSUE and ArtifactKind.ISSUE_COMMENT in enabled:
            number = _require_int_field(artifact.raw, "number")
            requests.append(
                GithubArtifactRequest(
                    operation=GithubCollectionOperation.LIST_ISSUE_COMMENTS,
                    artifact_kind=ArtifactKind.ISSUE_COMMENT,
                    target=f"{repository}#{number}",
                    command=(
                        "gh",
                        "api",
                        f"repos/{repository}/issues/{number}/comments?per_page=100",
                    ),
                )
            )

        if artifact.artifact_kind == ArtifactKind.CI_RUN and ArtifactKind.CI_JOB in enabled:
            database_id = _require_int_field(artifact.raw, "databaseId")
            requests.append(
                GithubArtifactRequest(
                    operation=GithubCollectionOperation.LIST_WORKFLOW_RUN_JOBS,
                    artifact_kind=ArtifactKind.CI_JOB,
                    target=f"{repository}/actions/runs/{database_id}",
                    command=(
                        "gh",
                        "run",
                        "view",
                        str(database_id),
                        "--repo",
                        repository,
                        "--json",
                        "jobs",
                    ),
                )
            )

    return tuple(requests)


def collect_github_artifacts(
    config: RepositoryConfig,
    *,
    runner: GhRunner = run_gh_command,
    fetched_at: datetime | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
    max_retries: int = 1,
) -> GithubCollectionReport:
    """Collect root and child GitHub artifacts with retryable error handling."""

    timestamp = fetched_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("fetched_at must include a timezone")
    fetched_at_text = timestamp.astimezone(timezone.utc).isoformat()

    artifacts: list[CollectedGithubArtifact] = []
    failures: list[GithubCollectionFailure] = []
    root_artifacts, root_failures = _run_requests(
        build_root_github_artifact_requests(config, limit=limit),
        runner=runner,
        repository_id=config.repository_id,
        fetched_at=fetched_at_text,
        max_retries=max_retries,
    )
    artifacts.extend(root_artifacts)
    failures.extend(root_failures)

    if root_artifacts:
        child_artifacts, child_failures = _run_requests(
            build_child_github_artifact_requests(config, tuple(root_artifacts)),
            runner=runner,
            repository_id=config.repository_id,
            fetched_at=fetched_at_text,
            max_retries=max_retries,
        )
        artifacts.extend(child_artifacts)
        failures.extend(child_failures)

    return GithubCollectionReport(
        repository_id=config.repository_id,
        fetched_at=fetched_at_text,
        artifacts=tuple(artifacts),
        failures=tuple(failures),
    )


def _run_requests(
    requests: tuple[GithubArtifactRequest, ...],
    *,
    runner: GhRunner,
    repository_id: str,
    fetched_at: str,
    max_retries: int,
) -> tuple[list[CollectedGithubArtifact], list[GithubCollectionFailure]]:
    artifacts: list[CollectedGithubArtifact] = []
    failures: list[GithubCollectionFailure] = []
    for request in requests:
        result, retry_count = _run_with_retries(request, runner, max_retries)
        if result.returncode != 0:
            error_type = classify_gh_error(result)
            failures.append(
                GithubCollectionFailure(
                    request=request,
                    error_type=error_type,
                    error_message=result.output,
                    retryable=_is_retryable(error_type),
                    retry_count=retry_count,
                )
            )
            continue
        artifacts.extend(
            _parse_artifacts(
                request,
                output=result.stdout,
                repository_id=repository_id,
                fetched_at=fetched_at,
            )
        )
    return artifacts, failures


def _run_with_retries(
    request: GithubArtifactRequest,
    runner: GhRunner,
    max_retries: int,
) -> tuple[GhCommandResult, int]:
    if max_retries < 0:
        raise ValueError("max_retries must not be negative")

    retry_count = 0
    while True:
        result = runner(request.command)
        if result.returncode == 0:
            return result, retry_count
        error_type = classify_gh_error(result)
        if not _is_retryable(error_type) or retry_count >= max_retries:
            return result, retry_count
        retry_count += 1


def _parse_artifacts(
    request: GithubArtifactRequest,
    *,
    output: str,
    repository_id: str,
    fetched_at: str,
) -> tuple[CollectedGithubArtifact, ...]:
    parsed = _parse_json_payload(output, request)
    records = _records_from_payload(request, parsed)
    return tuple(
        CollectedGithubArtifact(
            artifact_kind=request.artifact_kind,
            external_id=_external_id_for(request.artifact_kind, raw),
            source_url=_source_url_for(repository_id, request.artifact_kind, raw),
            fetched_at=fetched_at,
            raw=raw,
            request=request,
        )
        for raw in records
    )


def _parse_json_payload(output: str, request: GithubArtifactRequest) -> Any:
    try:
        return json.loads(output or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON for {request.operation.value}: {exc.msg}"
        ) from exc


def _records_from_payload(
    request: GithubArtifactRequest,
    payload: Any,
) -> tuple[dict[str, Any], ...]:
    if request.operation == GithubCollectionOperation.LIST_WORKFLOW_RUN_JOBS:
        if not isinstance(payload, dict):
            raise ValueError("workflow run jobs payload must be an object")
        jobs = payload.get("jobs", [])
        if not isinstance(jobs, list):
            raise ValueError("workflow run jobs payload jobs must be a list")
        return _require_object_list(jobs, request)

    if not isinstance(payload, list):
        raise ValueError(f"{request.operation.value} payload must be a list")
    return _require_object_list(payload, request)


def _require_object_list(
    values: list[Any],
    request: GithubArtifactRequest,
) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError(f"{request.operation.value} returned a non-object record")
        records.append(value)
    return tuple(records)


def _external_id_for(kind: ArtifactKind, raw: dict[str, Any]) -> str:
    if kind in {ArtifactKind.PULL_REQUEST, ArtifactKind.ISSUE}:
        return f"{kind.value}-{_require_int_field(raw, 'number')}"
    if kind in {
        ArtifactKind.REVIEW,
        ArtifactKind.REVIEW_COMMENT,
        ArtifactKind.ISSUE_COMMENT,
    }:
        return f"{kind.value}-{_require_id(raw)}"
    if kind == ArtifactKind.CI_RUN:
        return f"{kind.value}-{_require_int_field(raw, 'databaseId')}"
    if kind == ArtifactKind.CI_JOB:
        return f"{kind.value}-{_require_id(raw)}"
    raise ValueError(f"unsupported GitHub artifact kind: {kind.value}")


def _source_url_for(
    repository_id: str,
    kind: ArtifactKind,
    raw: dict[str, Any],
) -> str:
    url = raw.get("url") or raw.get("html_url")
    if isinstance(url, str) and url:
        return url
    if kind == ArtifactKind.PULL_REQUEST:
        return f"https://github.com/{repository_id}/pull/{_require_int_field(raw, 'number')}"
    if kind == ArtifactKind.ISSUE:
        return f"https://github.com/{repository_id}/issues/{_require_int_field(raw, 'number')}"
    return f"https://github.com/{repository_id}"


def _source_url_from_target(repository_id: str, target: str) -> str:
    if "#" in target:
        number = target.rsplit("#", 1)[-1]
        if number.isdigit():
            return f"https://github.com/{repository_id}/issues/{number}"
    if "/actions/runs/" in target:
        run_id = target.rsplit("/", 1)[-1]
        return f"https://github.com/{repository_id}/actions/runs/{run_id}"
    return f"https://github.com/{repository_id}"


def _require_int_field(raw: dict[str, Any], field: str) -> int:
    value = raw.get(field)
    if not isinstance(value, int):
        raise ValueError(f"artifact field must be an integer: {field}")
    return value


def _require_id(raw: dict[str, Any]) -> str:
    value = raw.get("id") or raw.get("databaseId")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value:
        return value
    raise ValueError("artifact must contain id or databaseId")


def _is_retryable(error_type: GhErrorType) -> bool:
    return error_type in {
        GhErrorType.NETWORK,
        GhErrorType.PROXY,
        GhErrorType.TLS_CERTIFICATE,
        GhErrorType.RATE_LIMIT,
        GhErrorType.UNKNOWN,
    }
