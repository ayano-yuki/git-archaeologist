"""Git history collection primitives.

The Git history collector reads immutable commit facts from a local clone and
turns them into Raw Archive-ready records. It keeps command execution isolated
behind a runner so tests can use small fixture repositories.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
import subprocess
from typing import Any

from git_archaeologist.raw_archive import (
    RawArtifact,
    canonical_json_bytes,
    error_report_payload,
    save_raw_artifact,
)


GIT_METADATA_SEPARATOR = "\x1f"
GIT_HISTORY_SCHEMA_VERSION = 1


class GitHistoryOperation(StrEnum):
    """Git operations used by the collector."""

    VERIFY_COMMIT = "verify_commit"
    READ_COMMIT_METADATA = "read_commit_metadata"
    READ_CHANGED_FILES = "read_changed_files"
    READ_DIFF = "read_diff"
    READ_TAGS = "read_tags"


class GitHistoryErrorType(StrEnum):
    """Human-actionable Git collection error classes."""

    PATH_OR_PERMISSION = "path_or_permission"
    CLONE_OR_FETCH_REQUIRED = "clone_or_fetch_required"
    GIT_COMMAND = "git_command"
    COMMIT_NOT_FOUND = "commit_not_found"


@dataclass(frozen=True)
class GitCommandResult:
    """Result from one git command."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def output(self) -> str:
        return "\n".join(part for part in (self.stdout, self.stderr) if part).strip()


GitRunner = callable


@dataclass(frozen=True)
class GitHistoryRequest:
    """One git command request."""

    operation: GitHistoryOperation
    repository_path: Path
    target: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class ChangedFile:
    """One file-level change reported by git name-status."""

    status: str
    path: str
    previous_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"status": self.status, "path": self.path}
        if self.previous_path:
            payload["previous_path"] = self.previous_path
        return payload


@dataclass(frozen=True)
class GitCommitArtifact:
    """Collected commit metadata, changed files, tags, and patch."""

    repository_id: str
    commit_sha: str
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    author_date: str
    committer_name: str
    committer_email: str
    committer_date: str
    subject: str
    body: str
    changed_files: tuple[ChangedFile, ...]
    diff: str
    tags: tuple[str, ...] = ()

    @property
    def source_url(self) -> str:
        return f"https://github.com/{self.repository_id}/commit/{self.commit_sha}"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": GIT_HISTORY_SCHEMA_VERSION,
            "repository_id": self.repository_id,
            "commit_sha": self.commit_sha,
            "parents": list(self.parents),
            "author": {
                "name": self.author_name,
                "email": self.author_email,
                "date": self.author_date,
            },
            "committer": {
                "name": self.committer_name,
                "email": self.committer_email,
                "date": self.committer_date,
            },
            "subject": self.subject,
            "body": self.body,
            "changed_files": [file_change.to_dict() for file_change in self.changed_files],
            "diff": self.diff,
            "tags": list(self.tags),
            "source_url": self.source_url,
            "policies": {
                "rename": "git name-status --find-renames records previous_path for R* entries",
                "merge": "all parents are retained; merge commits may have two or more parents",
                "tag": "tags pointing at the commit are collected with git tag --points-at",
                "blame": "blame is not stored in each commit artifact; later lineage collectors can run blame against the recorded SHA",
            },
        }

    def to_raw_artifact(self, *, retrieved_at: datetime) -> RawArtifact:
        return RawArtifact(
            repository_id=self.repository_id,
            artifact_kind="commit",
            external_id=f"commit-{self.commit_sha}",
            content=canonical_json_bytes(self.to_dict()),
            source_url=self.source_url,
            retrieved_at=retrieved_at,
        )


@dataclass(frozen=True)
class GitHistoryCollectionFailure:
    """Git collection failure suitable for human escalation."""

    request: GitHistoryRequest
    error_type: GitHistoryErrorType
    error_message: str

    def human_payload(self, repository_id: str) -> dict[str, object]:
        return error_report_payload(
            repository_id=repository_id,
            artifact_kind="commit",
            target=self.request.target,
            operation=self.request.operation.value,
            error_type=self.error_type.value,
            error_message=self.error_message,
            source_url=f"https://github.com/{repository_id}/commit/{self.request.target}",
        )


class GitHistoryCollectionError(RuntimeError):
    """Raised when a git command cannot produce a commit artifact."""

    def __init__(self, failure: GitHistoryCollectionFailure, repository_id: str) -> None:
        super().__init__(failure.error_message)
        self.failure = failure
        self.repository_id = repository_id

    def human_payload(self) -> dict[str, object]:
        return self.failure.human_payload(self.repository_id)


def run_git_command(command: Sequence[str]) -> GitCommandResult:
    """Run a git command and return captured text output."""

    completed = subprocess.run(
        tuple(command),
        check=False,
        text=True,
        capture_output=True,
    )
    return GitCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def collect_git_commit(
    repository_id: str,
    repository_path: str | Path,
    commit_sha: str,
    *,
    runner=run_git_command,
) -> GitCommitArtifact:
    """Collect one commit from a local git repository."""

    repo_path = Path(repository_path)
    if not repo_path.exists() or not repo_path.is_dir():
        request = _request(
            GitHistoryOperation.VERIFY_COMMIT,
            repo_path,
            commit_sha,
            ("git", "-C", str(repo_path), "rev-parse", "--show-toplevel"),
        )
        raise GitHistoryCollectionError(
            GitHistoryCollectionFailure(
                request=request,
                error_type=GitHistoryErrorType.PATH_OR_PERMISSION,
                error_message="repository_path does not exist or is not a directory",
            ),
            repository_id,
        )

    verified_sha = _run_required(
        repository_id,
        _request(
            GitHistoryOperation.VERIFY_COMMIT,
            repo_path,
            commit_sha,
            ("git", "-C", str(repo_path), "rev-parse", "--verify", f"{commit_sha}^{{commit}}"),
        ),
        runner,
    ).stdout.strip()

    metadata = _run_required(
        repository_id,
        _request(
            GitHistoryOperation.READ_COMMIT_METADATA,
            repo_path,
            verified_sha,
            (
                "git",
                "-C",
                str(repo_path),
                "show",
                "-s",
                f"--format=%H{GIT_METADATA_SEPARATOR}%P{GIT_METADATA_SEPARATOR}%an{GIT_METADATA_SEPARATOR}%ae{GIT_METADATA_SEPARATOR}%aI{GIT_METADATA_SEPARATOR}%cn{GIT_METADATA_SEPARATOR}%ce{GIT_METADATA_SEPARATOR}%cI{GIT_METADATA_SEPARATOR}%s{GIT_METADATA_SEPARATOR}%b",
                verified_sha,
            ),
        ),
        runner,
    ).stdout

    files = _run_required(
        repository_id,
        _request(
            GitHistoryOperation.READ_CHANGED_FILES,
            repo_path,
            verified_sha,
            (
                "git",
                "-C",
                str(repo_path),
                "show",
                "--no-ext-diff",
                "--format=",
                "--name-status",
                "--find-renames",
                verified_sha,
            ),
        ),
        runner,
    ).stdout

    diff = _run_required(
        repository_id,
        _request(
            GitHistoryOperation.READ_DIFF,
            repo_path,
            verified_sha,
            (
                "git",
                "-C",
                str(repo_path),
                "show",
                "--no-ext-diff",
                "--format=",
                "--find-renames",
                "--patch",
                verified_sha,
            ),
        ),
        runner,
    ).stdout

    tags = _run_required(
        repository_id,
        _request(
            GitHistoryOperation.READ_TAGS,
            repo_path,
            verified_sha,
            ("git", "-C", str(repo_path), "tag", "--points-at", verified_sha),
        ),
        runner,
    ).stdout

    parts = metadata.rstrip("\n").split(GIT_METADATA_SEPARATOR, 9)
    if len(parts) != 10:
        raise ValueError("git metadata output did not match expected schema")

    return GitCommitArtifact(
        repository_id=repository_id,
        commit_sha=parts[0],
        parents=tuple(parent for parent in parts[1].split() if parent),
        author_name=parts[2],
        author_email=parts[3],
        author_date=parts[4],
        committer_name=parts[5],
        committer_email=parts[6],
        committer_date=parts[7],
        subject=parts[8],
        body=parts[9],
        changed_files=parse_name_status(files),
        diff=diff,
        tags=tuple(tag for tag in tags.splitlines() if tag),
    )


def save_git_commit_to_raw_archive(
    archive_root: str | Path,
    artifact: GitCommitArtifact,
    *,
    retrieved_at: datetime,
):
    """Save a collected commit into Raw Archive storage."""

    return save_raw_artifact(
        archive_root,
        artifact.to_raw_artifact(retrieved_at=retrieved_at),
    )


def parse_name_status(output: str) -> tuple[ChangedFile, ...]:
    """Parse git name-status output, including rename rows."""

    changes: list[ChangedFile] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R"):
            if len(parts) != 3:
                raise ValueError("rename name-status row must include old and new path")
            changes.append(ChangedFile(status=status, previous_path=parts[1], path=parts[2]))
            continue
        if len(parts) != 2:
            raise ValueError("name-status row must include status and path")
        changes.append(ChangedFile(status=status, path=parts[1]))
    return tuple(changes)


def classify_git_error(result: GitCommandResult) -> GitHistoryErrorType:
    output = result.output.lower()
    if "not a git repository" in output or "no such file" in output:
        return GitHistoryErrorType.CLONE_OR_FETCH_REQUIRED
    if "needed a single revision" in output or "unknown revision" in output:
        return GitHistoryErrorType.COMMIT_NOT_FOUND
    if "permission denied" in output:
        return GitHistoryErrorType.PATH_OR_PERMISSION
    return GitHistoryErrorType.GIT_COMMAND


def _run_required(
    repository_id: str,
    request: GitHistoryRequest,
    runner,
) -> GitCommandResult:
    result = runner(request.command)
    if result.returncode == 0:
        return result
    raise GitHistoryCollectionError(
        GitHistoryCollectionFailure(
            request=request,
            error_type=classify_git_error(result),
            error_message=result.output,
        ),
        repository_id,
    )


def _request(
    operation: GitHistoryOperation,
    repository_path: Path,
    target: str,
    command: tuple[str, ...],
) -> GitHistoryRequest:
    return GitHistoryRequest(
        operation=operation,
        repository_path=repository_path,
        target=target,
        command=command,
    )
