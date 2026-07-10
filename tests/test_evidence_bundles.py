from llm_tuning_lab.data.bundles import build_evidence_bundles


def test_bundle_grouping_combines_issue_pr_commit_and_review() -> None:
    records = [
        {
            "repo": "acme/project",
            "kind": "pull",
            "number": 10,
            "data": {
                "number": 10,
                "title": "Keep auth sync",
                "body": "Fixes ordering around token refresh.",
                "created_at": "2026-01-01T00:00:00Z",
            },
        },
        {
            "repo": "acme/project",
            "kind": "pull_commit",
            "data": {
                "_parent_pull_number": 10,
                "sha": "abc",
                "commit": {"message": "Keep auth calls synchronous"},
            },
        },
        {
            "repo": "acme/project",
            "kind": "pull_review",
            "data": {
                "_parent_pull_number": 10,
                "body": "Avoid async refresh races.",
                "state": "APPROVED",
            },
        },
        {
            "repo": "acme/project",
            "kind": "pull_file",
            "data": {
                "_parent_pull_number": 10,
                "filename": "auth.py",
                "status": "modified",
                "patch": "@@ sync call remains",
            },
        },
    ]

    bundles = build_evidence_bundles(records, min_evidence_per_bundle=3)

    assert len(bundles) == 1
    assert bundles[0]["thread_key"] == "pull:10"
    assert {item["kind"] for item in bundles[0]["evidence"]} >= {
        "pull",
        "pull_commit",
        "pull_review",
        "pull_file",
    }


def test_revert_commit_adds_derived_revert_evidence() -> None:
    records = [
        {
            "repo": "acme/project",
            "kind": "commit",
            "data": {"sha": "abc", "commit": {"message": "Merge pull request #10"}},
        },
        {
            "repo": "acme/project",
            "kind": "pull",
            "number": 10,
            "data": {"number": 10, "title": "Change cache", "body": "Change behavior."},
        },
        {
            "repo": "acme/project",
            "kind": "pull_commit",
            "data": {"_parent_pull_number": 10, "commit": {"message": "Revert cache change"}},
        },
    ]

    bundles = build_evidence_bundles(records, min_evidence_per_bundle=3)

    assert any(item["kind"] == "revert_relation" for item in bundles[0]["evidence"])
