from __future__ import annotations

import unittest

from git_archaeologist.normalization.common_events import (
    ArtifactReference,
    CommonEvent,
    EventFieldSet,
    EventKind,
    EvidenceKind,
    RelationKind,
)
from git_archaeologist.normalization.event_graph import generate_event_graph_edges


class EventGraphTests(unittest.TestCase):
    def test_generates_pr_to_commit_edge_from_merge_sha(self) -> None:
        commit = _event(
            "commit-1",
            EventKind.COMMIT,
            EvidenceKind.GIT_COMMIT,
            commit_sha="abc1234",
        )
        pr = _event(
            "pr-1",
            EventKind.PULL_REQUEST,
            EvidenceKind.GITHUB_PULL_REQUEST,
            pull_request_number=10,
            extracted=EventFieldSet(commit_sha="abc1234"),
        )

        edges = generate_event_graph_edges((commit, pr))

        self.assertTrue(
            any(
                edge.source_event_id == "pr-1"
                and edge.target_event_id == "commit-1"
                and edge.relation.relation_kind == RelationKind.IMPLEMENTS
                for edge in edges
            )
        )

    def test_generates_issue_reference_edge(self) -> None:
        issue = _event("issue-7", EventKind.ISSUE, EvidenceKind.GITHUB_ISSUE, issue_number=7)
        pr = _event(
            "pr-1",
            EventKind.PULL_REQUEST,
            EvidenceKind.GITHUB_PULL_REQUEST,
            pull_request_number=10,
            body="Fixes #7 by adding a guard.",
        )

        edges = generate_event_graph_edges((issue, pr))

        edge = next(edge for edge in edges if edge.target_event_id == "issue-7")
        self.assertEqual(RelationKind.CLOSES, edge.relation.relation_kind)
        self.assertFalse(edge.relation.inferred)
        self.assertIn("issue #7", edge.relation.rationale or "")

    def test_generates_ci_to_commit_edge_from_head_sha(self) -> None:
        commit = _event(
            "commit-1",
            EventKind.COMMIT,
            EvidenceKind.GIT_COMMIT,
            commit_sha="def5678",
        )
        ci = _event(
            "ci-1",
            EventKind.CI,
            EvidenceKind.GITHUB_ACTIONS_RUN,
            commit_sha="def5678",
        )

        edges = generate_event_graph_edges((commit, ci))

        self.assertTrue(
            any(
                edge.source_event_id == "ci-1"
                and edge.target_event_id == "commit-1"
                and edge.relation.relation_kind == RelationKind.TRIGGERS
                for edge in edges
            )
        )

    def test_same_file_relation_is_inferred_with_lower_confidence(self) -> None:
        first = _event(
            "commit-1",
            EventKind.COMMIT,
            EvidenceKind.GIT_COMMIT,
            commit_sha="abc1234",
            file_path="packages/react/src/ReactHooks.js",
        )
        second = _event(
            "review-1",
            EventKind.REVIEW,
            EvidenceKind.GITHUB_REVIEW,
            file_path="packages/react/src/ReactHooks.js",
        )

        edges = generate_event_graph_edges((first, second))
        inferred = [
            edge
            for edge in edges
            if edge.relation.relation_kind == RelationKind.POSSIBLY_RELATED
        ]

        self.assertTrue(inferred)
        self.assertTrue(all(edge.relation.inferred for edge in inferred))
        self.assertTrue(all(edge.relation.confidence < 1.0 for edge in inferred))


def _event(
    event_id: str,
    kind: EventKind,
    evidence_kind: EvidenceKind,
    *,
    commit_sha: str | None = None,
    pull_request_number: int | None = None,
    issue_number: int | None = None,
    file_path: str | None = None,
    body: str | None = None,
    extracted: EventFieldSet | None = None,
) -> CommonEvent:
    return CommonEvent(
        event_id=event_id,
        kind=kind,
        source_url="https://github.com/react/react",
        evidence_kind=evidence_kind,
        observed=EventFieldSet(
            occurred_at="2026-07-26T00:00:00Z",
            actor="maintainer",
            commit_sha=commit_sha,
            pull_request_number=pull_request_number,
            issue_number=issue_number,
            file_path=file_path,
            body=body,
        ),
        extracted=extracted or EventFieldSet(),
        artifact_references=(
            ArtifactReference(
                artifact_kind=evidence_kind,
                artifact_id=event_id,
                source_url="https://github.com/react/react",
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
