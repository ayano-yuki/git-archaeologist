from __future__ import annotations

import unittest

from git_archaeologist.common_events import EventKind, EvidenceKind
from git_archaeologist.normalizers import (
    NormalizationFailure,
    NormalizationSuccess,
    RawArtifactEnvelope,
    normalize_artifact,
    stable_event_id,
)


class ArtifactNormalizerTests(unittest.TestCase):
    def test_normalizes_mvp_artifact_kinds_to_common_events(self) -> None:
        samples = [
            _artifact(
                EvidenceKind.GITHUB_PULL_REQUEST,
                "pull_request-123",
                {
                    "number": 123,
                    "title": "Fix scheduler",
                    "body": "Discussion body",
                    "author": {"login": "maintainer"},
                    "createdAt": "2026-07-26T00:00:00Z",
                },
            ),
            _artifact(
                EvidenceKind.GITHUB_ISSUE,
                "issue-456",
                {
                    "number": 456,
                    "title": "Bug",
                    "author": {"login": "reporter"},
                    "createdAt": "2026-07-26T00:00:00Z",
                },
            ),
            _artifact(
                EvidenceKind.GITHUB_REVIEW,
                "review-1",
                {
                    "pull_request_number": 123,
                    "body": "Looks good",
                    "author": {"login": "reviewer"},
                    "createdAt": "2026-07-26T00:00:00Z",
                },
            ),
            _artifact(
                EvidenceKind.GIT_COMMIT,
                "commit-abc1234",
                {
                    "commit_sha": "abc1234",
                    "author_name": "Dev",
                    "author_date": "2026-07-26T00:00:00Z",
                    "subject": "Fix bug",
                },
            ),
            _artifact(
                EvidenceKind.GITHUB_ACTIONS_RUN,
                "ci_run-99",
                {
                    "headSha": "def5678",
                    "displayTitle": "CI",
                    "createdAt": "2026-07-26T00:00:00Z",
                },
            ),
        ]

        results = [normalize_artifact(sample) for sample in samples]

        self.assertTrue(all(isinstance(result, NormalizationSuccess) for result in results))
        kinds = [result.event.kind for result in results if isinstance(result, NormalizationSuccess)]
        self.assertEqual(
            [
                EventKind.PULL_REQUEST,
                EventKind.ISSUE,
                EventKind.REVIEW,
                EventKind.COMMIT,
                EventKind.CI,
            ],
            kinds,
        )

    def test_generates_stable_event_id_for_same_raw_artifact(self) -> None:
        artifact = _artifact(
            EvidenceKind.GITHUB_PULL_REQUEST,
            "pull_request-123",
            {"number": 123, "createdAt": "2026-07-26T00:00:00Z"},
        )

        self.assertEqual(stable_event_id(artifact), stable_event_id(artifact))

    def test_returns_failure_with_quarantine_payload_for_missing_timestamp(self) -> None:
        artifact = _artifact(
            EvidenceKind.GITHUB_ISSUE,
            "issue-456",
            {"number": 456, "title": "Missing time"},
        )

        result = normalize_artifact(artifact)

        self.assertIsInstance(result, NormalizationFailure)
        assert isinstance(result, NormalizationFailure)
        payload = result.human_payload()
        self.assertEqual("react/react", payload["repository_id"])
        self.assertEqual("github_issue", payload["artifact_kind"])
        self.assertIn("missing observed timestamp", payload["error_message"])
        self.assertIn("quarantine", payload["quarantine_path"])

    def test_rejects_unsupported_artifact_kind_without_throwing(self) -> None:
        artifact = _artifact(
            EvidenceKind.GIT_BLAME,
            "blame-1",
            {"createdAt": "2026-07-26T00:00:00Z"},
        )

        result = normalize_artifact(artifact)

        self.assertIsInstance(result, NormalizationFailure)
        assert isinstance(result, NormalizationFailure)
        self.assertIn("unsupported artifact kind", result.reason)


def _artifact(
    kind: EvidenceKind,
    artifact_id: str,
    raw: dict[str, object],
) -> RawArtifactEnvelope:
    return RawArtifactEnvelope(
        repository_id="react/react",
        artifact_kind=kind,
        artifact_id=artifact_id,
        source_url="https://github.com/react/react",
        raw=raw,
        raw_path=f"raw/react-react/{kind.value}/{artifact_id}.json",
        content_hash="sha256:sample",
    )


if __name__ == "__main__":
    unittest.main()
