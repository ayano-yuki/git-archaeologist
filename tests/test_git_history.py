from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from git_archaeologist.git_history import (
    GitCommandResult,
    GitHistoryCollectionError,
    GitHistoryErrorType,
    collect_git_commit,
    parse_name_status,
    save_git_commit_to_raw_archive,
)


class GitHistoryCollectorTests(unittest.TestCase):
    def test_collects_commit_metadata_parent_diff_and_changed_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir))
            first_sha = _commit_file(repo, "README.md", "hello\n", "initial commit")
            second_sha = _commit_file(repo, "README.md", "hello\nworld\n", "update readme")

            artifact = collect_git_commit("react/react", repo, second_sha)

            self.assertEqual(second_sha, artifact.commit_sha)
            self.assertEqual((first_sha,), artifact.parents)
            self.assertEqual("update readme", artifact.subject)
            self.assertEqual("README.md", artifact.changed_files[0].path)
            self.assertIn("+world", artifact.diff)
            self.assertEqual(
                f"https://github.com/react/react/commit/{second_sha}",
                artifact.source_url,
            )

    def test_saves_collected_commit_to_raw_archive(self) -> None:
        with TemporaryDirectory() as repo_dir, TemporaryDirectory() as archive_dir:
            repo = _init_repo(Path(repo_dir))
            sha = _commit_file(repo, "file.txt", "content\n", "add file")
            artifact = collect_git_commit("react/react", repo, sha)

            result = save_git_commit_to_raw_archive(
                archive_dir,
                artifact,
                retrieved_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            )

            self.assertTrue(result.wrote_content)
            self.assertEqual("commit", result.manifest_record.artifact_kind)
            self.assertEqual(f"commit-{sha}", result.manifest_record.external_id)
            self.assertTrue(result.content_path.read_text(encoding="utf-8"))

    def test_records_rename_rows_with_previous_path(self) -> None:
        changes = parse_name_status("R100\told.py\tnew.py\nM\tREADME.md\n")

        self.assertEqual("R100", changes[0].status)
        self.assertEqual("old.py", changes[0].previous_path)
        self.assertEqual("new.py", changes[0].path)
        self.assertEqual("M", changes[1].status)

    def test_reports_missing_repository_as_human_action_payload(self) -> None:
        with self.assertRaises(GitHistoryCollectionError) as raised:
            collect_git_commit("react/react", "missing-repository", "HEAD")

        payload = raised.exception.human_payload()
        self.assertEqual("react/react", payload["repository_id"])
        self.assertEqual("commit", payload["artifact_kind"])
        self.assertEqual("path_or_permission", payload["error_type"])
        self.assertEqual("verify_commit", payload["operation"])

    def test_classifies_unknown_commit_failure(self) -> None:
        def fake_runner(command: tuple[str, ...]) -> GitCommandResult:
            return GitCommandResult(
                returncode=1,
                stderr="fatal: needed a single revision",
            )

        with TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir))
            with self.assertRaises(GitHistoryCollectionError) as raised:
                collect_git_commit("react/react", repo, "does-not-exist", runner=fake_runner)

        self.assertEqual(
            GitHistoryErrorType.COMMIT_NOT_FOUND.value,
            raised.exception.human_payload()["error_type"],
        )


def _init_repo(path: Path) -> Path:
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    return path


def _commit_file(repo: Path, relative_path: str, content: str, message: str) -> str:
    file_path = repo / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    _git(repo, "add", relative_path)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").strip()


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo), *args),
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


if __name__ == "__main__":
    unittest.main()
