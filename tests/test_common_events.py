from __future__ import annotations

import json
import unittest

from git_archaeologist.common_events import (
    COMMON_EVENT_SCHEMA_VERSION,
    ArtifactReference,
    CommonEvent,
    EventFieldSet,
    EventKind,
    EventRelation,
    EvidenceKind,
    RelationKind,
    build_conversion_failure_report,
    validate_common_event,
)


class CommonEventTests(unittest.TestCase):
    def test_schema_represents_all_mvp_artifact_event_kinds(self) -> None:
        samples = {
            EventKind.COMMIT: _event(
                "commit-react-react-abc1234",
                EventKind.COMMIT,
                EvidenceKind.GIT_COMMIT,
                commit_sha="abc1234",
            ),
            EventKind.PULL_REQUEST: _event(
                "pr-react-react-1000",
                EventKind.PULL_REQUEST,
                EvidenceKind.GITHUB_PULL_REQUEST,
                pull_request_number=1000,
            ),
            EventKind.ISSUE: _event(
                "issue-react-react-2000",
                EventKind.ISSUE,
                EvidenceKind.GITHUB_ISSUE,
                issue_number=2000,
            ),
            EventKind.REVIEW: _event(
                "review-react-react-3000",
                EventKind.REVIEW,
                EvidenceKind.GITHUB_REVIEW,
                pull_request_number=1000,
            ),
            EventKind.CI: _event(
                "ci-react-react-4000",
                EventKind.CI,
                EvidenceKind.GITHUB_ACTIONS_RUN,
                commit_sha="def5678",
            ),
            EventKind.REVERT: _event(
                "revert-react-react-5000",
                EventKind.REVERT,
                EvidenceKind.GIT_COMMIT,
                commit_sha="deadbee",
                relations=(
                    EventRelation(
                        relation_kind=RelationKind.REVERTS,
                        target_event_id="commit-react-react-abc1234",
                        evidence_kind=EvidenceKind.GIT_COMMIT,
                    ),
                ),
            ),
        }

        self.assertEqual(set(EventKind), set(samples))
        for event in samples.values():
            with self.subTest(kind=event.kind):
                payload = validate_common_event(event.to_dict()).to_dict()

                self.assertEqual(COMMON_EVENT_SCHEMA_VERSION, payload["schema_version"])
                self.assertEqual(event.kind.value, payload["kind"])
                self.assertIn("observed", payload)
                self.assertIn("artifact_references", payload)

    def test_keeps_observed_extracted_and_inferred_values_separate(self) -> None:
        event = _event(
            "pr-react-react-1000",
            EventKind.PULL_REQUEST,
            EvidenceKind.GITHUB_PULL_REQUEST,
            pull_request_number=1000,
            extracted=EventFieldSet(
                file_path="packages/react/src/ReactHooks.js",
                symbol_name="use",
                diff_hunk="@@ -1,2 +1,3 @@",
            ),
            inferred=EventFieldSet(issue_number=2000),
            relations=(
                EventRelation(
                    relation_kind=RelationKind.POSSIBLY_RELATED,
                    target_event_id="issue-react-react-2000",
                    evidence_kind=EvidenceKind.GITHUB_COMMENT,
                    confidence=0.45,
                    source_url="https://github.com/facebook/react/pull/1000",
                    rationale="Issue number appeared in discussion text.",
                    inferred=True,
                ),
            ),
        )

        payload = event.to_dict()

        self.assertEqual(1000, payload["observed"]["pull_request_number"])
        self.assertEqual("use", payload["extracted"]["symbol_name"])
        self.assertEqual(2000, payload["inferred"]["issue_number"])
        self.assertTrue(payload["relations"][0]["inferred"])
        self.assertLess(payload["relations"][0]["confidence"], 1.0)

    def test_validates_source_url_and_artifact_references(self) -> None:
        event = _event(
            "commit-react-react-abc1234",
            EventKind.COMMIT,
            EvidenceKind.GIT_DIFF,
            commit_sha="abc1234",
        )

        payload = event.to_dict()
        self.assertEqual("https://github.com/facebook/react/commit/abc1234", payload["source_url"])
        self.assertEqual("raw/react-react/git_diff/abc1234.json", payload["artifact_references"][0]["raw_path"])

    def test_to_dict_is_json_serializable(self) -> None:
        serialized = json.dumps(
            _event(
                "issue-react-react-2000",
                EventKind.ISSUE,
                EvidenceKind.GITHUB_ISSUE,
                issue_number=2000,
            ).to_dict(),
            sort_keys=True,
        )

        self.assertIn('"kind": "issue"', serialized)
        self.assertIn('"schema_version": 1', serialized)

    def test_rejects_event_without_observed_time(self) -> None:
        with self.assertRaisesRegex(ValueError, "observed.occurred_at"):
            CommonEvent(
                event_id="commit-react-react-abc1234",
                kind=EventKind.COMMIT,
                source_url="https://github.com/facebook/react/commit/abc1234",
                evidence_kind=EvidenceKind.GIT_COMMIT,
                observed=EventFieldSet(commit_sha="abc1234"),
                artifact_references=(
                    ArtifactReference(
                        artifact_kind=EvidenceKind.GIT_COMMIT,
                        artifact_id="abc1234",
                        source_url="https://github.com/facebook/react/commit/abc1234",
                    ),
                ),
            )

    def test_rejects_invalid_inferred_relation_confidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "inferred relations"):
            EventRelation(
                relation_kind=RelationKind.POSSIBLY_RELATED,
                target_event_id="issue-react-react-2000",
                evidence_kind=EvidenceKind.GITHUB_COMMENT,
                inferred=True,
            ).validate()

    def test_validate_common_event_rejects_unknown_schema_version(self) -> None:
        payload = _event(
            "ci-react-react-4000",
            EventKind.CI,
            EvidenceKind.GITHUB_ACTIONS_RUN,
            commit_sha="def5678",
        ).to_dict()
        payload["schema_version"] = 999

        with self.assertRaisesRegex(ValueError, "unsupported common event"):
            validate_common_event(payload)

    def test_conversion_failure_report_contains_human_action_payload(self) -> None:
        report = build_conversion_failure_report(
            repository_id="react/react",
            artifact_kind=EvidenceKind.GITHUB_PULL_REQUEST,
            target="pull_request:1000",
            operation="normalize_common_event",
            error=ValueError("missing required field: observed"),
            source_url="https://github.com/facebook/react/pull/1000",
            quarantine_path="data/Qwen--Qwen2.5-Coder-7B-Instruct/processed/quarantine/pr-1000.json",
            retry_count=1,
        )

        payload = report.to_dict()

        self.assertEqual("react/react", payload["repository_id"])
        self.assertEqual("github_pull_request", payload["artifact_kind"])
        self.assertEqual("ValueError", payload["error_type"])
        self.assertIn("missing required field", payload["error_message"])
        self.assertIn("quarantine", payload["quarantine_path"])
        self.assertEqual(1, payload["retry_count"])


def _event(
    event_id: str,
    kind: EventKind,
    evidence_kind: EvidenceKind,
    *,
    commit_sha: str | None = None,
    pull_request_number: int | None = None,
    issue_number: int | None = None,
    extracted: EventFieldSet | None = None,
    inferred: EventFieldSet | None = None,
    relations: tuple[EventRelation, ...] = (),
) -> CommonEvent:
    artifact_id = (
        commit_sha
        or str(pull_request_number)
        or str(issue_number)
        or event_id.removeprefix(f"{kind.value}-")
    )
    source_url = _source_url(kind, artifact_id)
    return CommonEvent(
        event_id=event_id,
        kind=kind,
        source_url=source_url,
        evidence_kind=evidence_kind,
        observed=EventFieldSet(
            occurred_at="2026-07-26T12:00:00+09:00",
            actor="react-maintainer",
            commit_sha=commit_sha,
            pull_request_number=pull_request_number,
            issue_number=issue_number,
            title=f"Sample {kind.value}",
            body="Observed raw artifact body.",
        ),
        extracted=extracted or EventFieldSet(),
        inferred=inferred or EventFieldSet(),
        artifact_references=(
            ArtifactReference(
                artifact_kind=evidence_kind,
                artifact_id=artifact_id,
                source_url=source_url,
                raw_path=f"raw/react-react/{evidence_kind.value}/{artifact_id}.json",
                content_hash="sha256:sample",
            ),
        ),
        relations=relations,
    )


def _source_url(kind: EventKind, artifact_id: str) -> str:
    if kind in {EventKind.COMMIT, EventKind.REVERT}:
        return f"https://github.com/facebook/react/commit/{artifact_id}"
    if kind in {EventKind.PULL_REQUEST, EventKind.REVIEW}:
        return f"https://github.com/facebook/react/pull/{artifact_id}"
    if kind is EventKind.ISSUE:
        return f"https://github.com/facebook/react/issues/{artifact_id}"
    return f"https://github.com/facebook/react/actions/runs/{artifact_id}"


if __name__ == "__main__":
    unittest.main()
