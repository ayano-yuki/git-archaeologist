from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from git_archaeologist.raw_archive import (
    HUMAN_ERROR_SUPPRESSED_FIELDS,
    RAW_ARCHIVE_SCHEMA_VERSION,
    RawArchiveStorageError,
    RawArtifact,
    RedactionMarkers,
    build_manifest_record,
    canonical_json_bytes,
    content_hash,
    error_report_payload,
    redacted_secret_marker,
    save_raw_artifact,
    stable_artifact_path,
    suppressed_secret_marker,
)


class RawArchiveTests(unittest.TestCase):
    def test_stable_artifact_path_uses_repository_kind_and_external_id(self) -> None:
        path = stable_artifact_path(
            "react/react",
            "pull_request",
            "pr-1000",
        )

        self.assertEqual(path, Path("react") / "react" / "pull_request" / "pr-1000.json")

    def test_stable_artifact_path_encodes_external_slashes(self) -> None:
        path = stable_artifact_path(
            "react/react",
            "review_comment",
            "pull/1000#discussion_r1",
        )

        self.assertEqual(
            path,
            Path("react")
            / "react"
            / "review_comment"
            / "pull%2F1000%23discussion_r1.json",
        )

    def test_content_hash_uses_sha256_prefix(self) -> None:
        content = b'{"number":1000}'

        digest = content_hash(content)

        self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(digest, content_hash(content))
        self.assertNotEqual(digest, content_hash(b'{"number":1001}'))

    def test_manifest_record_schema_includes_redaction_markers(self) -> None:
        artifact = _sample_artifact(
            redaction=RedactionMarkers(
                redacted_labels=("token",),
                suppressed_fields=("authorization_header",),
            )
        )

        record = build_manifest_record(artifact)
        payload = record.to_dict()

        self.assertEqual(payload["schema_version"], RAW_ARCHIVE_SCHEMA_VERSION)
        self.assertEqual(payload["repository_id"], "react/react")
        self.assertEqual(payload["artifact_kind"], "pull_request")
        self.assertEqual(payload["external_id"], "pr-1000")
        self.assertEqual(payload["archive_path"], "react/react/pull_request/pr-1000.json")
        self.assertEqual(payload["byte_size"], len(artifact.content))
        self.assertEqual(payload["content_hash"], content_hash(artifact.content))
        self.assertEqual(payload["retrieved_at"], "2026-07-26T01:02:03Z")
        self.assertEqual(
            payload["redaction"],
            {
                "has_redactions": True,
                "redacted_labels": ["token"],
                "suppressed_fields": ["authorization_header"],
                "redacted_markers": ["[REDACTED:token]"],
                "suppressed_markers": ["[SUPPRESSED:authorization_header]"],
            },
        )

    def test_save_raw_artifact_writes_once_and_reports_duplicate_rerun(self) -> None:
        artifact = _sample_artifact()

        with TemporaryDirectory() as temp_dir:
            first = save_raw_artifact(temp_dir, artifact)
            second = save_raw_artifact(temp_dir, artifact)

            self.assertTrue(first.wrote_content)
            self.assertFalse(first.duplicate)
            self.assertFalse(second.wrote_content)
            self.assertTrue(second.duplicate)
            self.assertEqual(first.content_path, second.content_path)
            self.assertEqual(first.content_path.read_bytes(), artifact.content)
            self.assertEqual(
                second.manifest_record.to_dict(),
                first.manifest_record.to_dict(),
            )

    def test_save_raw_artifact_rejects_same_path_with_different_content(self) -> None:
        first_artifact = _sample_artifact()
        changed_artifact = _sample_artifact(content=canonical_json_bytes({"number": 1001}))

        with TemporaryDirectory() as temp_dir:
            save_raw_artifact(temp_dir, first_artifact)

            with self.assertRaises(RawArchiveStorageError) as raised:
                save_raw_artifact(temp_dir, changed_artifact)

        payload = raised.exception.human_payload()
        self.assertEqual(payload["repository_id"], "react/react")
        self.assertEqual(payload["artifact_kind"], "pull_request")
        self.assertEqual(payload["target"], "pr-1000")
        self.assertEqual(payload["operation"], "save_raw_artifact")
        self.assertEqual(payload["error_type"], "storage_integrity_error")
        self.assertIn("different content hash", payload["error_message"])
        self.assertIn("authorization_header", payload["suppressed_fields"])

    def test_error_report_payload_suppresses_secret_fields_from_extra(self) -> None:
        payload = error_report_payload(
            repository_id="react/react",
            artifact_kind="ci_run",
            target="run-123",
            operation="collect",
            error_type="redaction_or_secret_detection",
            error_message="secret-like value was suppressed",
            source_url="https://github.com/react/react/actions/runs/123",
            retry_count=1,
            extra={
                "authorization_header": "Bearer should-not-leak",
                "raw_token": "should-not-leak",
                "safe_note": "collector stopped before save",
            },
        )

        self.assertEqual(set(HUMAN_ERROR_SUPPRESSED_FIELDS), {
            "raw_token",
            "authorization_header",
            "secret_value",
            "private_key",
        })
        self.assertNotIn("authorization_header", payload)
        self.assertNotIn("raw_token", payload)
        self.assertEqual(payload["safe_note"], "collector stopped before save")
        self.assertEqual(
            payload["suppressed_fields"],
            list(HUMAN_ERROR_SUPPRESSED_FIELDS),
        )

    def test_redaction_and_suppression_marker_helpers_are_stable(self) -> None:
        self.assertEqual(redacted_secret_marker(), "[REDACTED:secret]")
        self.assertEqual(redacted_secret_marker("token"), "[REDACTED:token]")
        self.assertEqual(suppressed_secret_marker(), "[SUPPRESSED:secret]")
        self.assertEqual(
            suppressed_secret_marker("authorization_header"),
            "[SUPPRESSED:authorization_header]",
        )


def _sample_artifact(
    *,
    content: bytes | None = None,
    redaction: RedactionMarkers | None = None,
) -> RawArtifact:
    return RawArtifact(
        repository_id="react/react",
        artifact_kind="pull_request",
        external_id="pr-1000",
        content=content or canonical_json_bytes({"number": 1000, "title": "Example"}),
        source_url="https://github.com/react/react/pull/1000",
        retrieved_at=datetime(2026, 7, 26, 1, 2, 3, tzinfo=timezone.utc),
        redaction=redaction or RedactionMarkers(),
    )


if __name__ == "__main__":
    unittest.main()
