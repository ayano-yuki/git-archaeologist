import json

from llm_tuning_lab.data.gold_cases import (
    bundle_hash,
    evidence_hash,
    materialize_sft_records,
    split_gold_cases,
    validate_sft_record_budget,
    validate_gold_cases,
)


def test_gold_case_validation_rejects_invented_citation() -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    case = _case(bundle, ["e1", "missing"])

    result = validate_gold_cases({"bundle-a": bundle}, [case])

    assert not result.ok
    assert any("citations not found" in error for error in result.errors)


def test_gold_case_validation_rejects_missing_fact_citation() -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    case = _case(bundle, ["e1", "e2"])
    case["facts"] = [{"text": "The PR kept sync auth."}]

    result = validate_gold_cases({"bundle-a": bundle}, [case])

    assert not result.ok
    assert any("must cite evidence" in error for error in result.errors)


def test_gold_case_validation_rejects_malformed_timeline() -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    case = _case(bundle, ["e1", "e2"])
    case["timeline"] = [
        {"date": "2026-02-01T00:00:00Z", "text": "Second", "citations": ["e2"]},
        {"date": "2026-01-01T00:00:00Z", "text": "First", "citations": ["e1"]},
    ]

    result = validate_gold_cases({"bundle-a": bundle}, [case])

    assert not result.ok
    assert any("chronological" in error for error in result.errors)


def test_gold_case_validation_rejects_missing_text_and_review_metadata() -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    case = _case(bundle, ["e1", "e2"])
    case["facts"] = [{"citations": ["e1"]}]
    case["timeline"] = [{"date": "2026-01-01T00:00:00Z", "text": "", "citations": []}]
    case.pop("reviewer_id")

    result = validate_gold_cases({"bundle-a": bundle}, [case])

    assert not result.ok
    assert any("facts[1].text" in error for error in result.errors)
    assert any("timeline[1].text" in error for error in result.errors)
    assert any("timeline[1] must cite evidence" in error for error in result.errors)
    assert any("reviewer_id" in error for error in result.errors)


def test_materialize_sft_records_only_includes_approved_cases() -> None:
    bundles = {"bundle-a": _bundle("bundle-a", "pull:1", ["e1", "e2"])}
    approved = _case(bundles["bundle-a"], ["e1", "e2"])
    draft = _case(bundles["bundle-a"], ["e1", "e2"])
    draft["review_status"] = "draft"

    records = materialize_sft_records(bundles, [approved, draft])

    assert len(records) == 1
    assert records[0]["messages"][0]["role"] == "system"
    assert "Evidence:" in records[0]["messages"][1]["content"]
    assistant = json.loads(records[0]["messages"][2]["content"])
    assert assistant["schema_version"] == "git-archaeologist.answer.v1"
    assert assistant["answer"] == approved["answer"]


def test_thread_hash_split_keeps_same_thread_in_one_split() -> None:
    bundles = {
        "bundle-a": _bundle("bundle-a", "pull:1", ["e1", "e2"]),
        "bundle-b": _bundle("bundle-b", "pull:1", ["e3", "e4"]),
    }
    cases = [_case(bundles["bundle-a"], ["e1", "e2"]), _case(bundles["bundle-b"], ["e3", "e4"])]

    splits = split_gold_cases(bundles, cases, validation_ratio=0.4, test_ratio=0.4)
    locations = [name for name, split_cases in splits.items() if split_cases for _ in split_cases]

    assert len(set(locations)) == 1


def test_repository_holdout_split_keeps_unknown_repo_for_test() -> None:
    bundles = {
        "bundle-a": _bundle("bundle-a", "pull:1", ["e1", "e2"], repo="train/repo"),
        "bundle-b": _bundle("bundle-b", "pull:2", ["e3", "e4"], repo="test/repo"),
    }
    cases = [_case(bundles["bundle-a"], ["e1", "e2"]), _case(bundles["bundle-b"], ["e3", "e4"])]

    splits = split_gold_cases(
        bundles,
        cases,
        split_strategy="repository_holdout",
        test_repositories=["test/repo"],
    )

    assert splits["train"] == [cases[0]]
    assert splits["test"] == [cases[1]]


def test_repository_holdout_rejects_missing_test_repository() -> None:
    bundles = {
        "bundle-a": _bundle("bundle-a", "pull:1", ["e1", "e2"], repo="train/repo"),
    }
    cases = [_case(bundles["bundle-a"], ["e1", "e2"])]

    try:
        split_gold_cases(
            bundles,
            cases,
            split_strategy="repository_holdout",
            test_repositories=["missing/repo"],
        )
    except ValueError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected repository holdout to reject missing repository")


def test_sft_record_budget_rejects_overflow() -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    case = _case(bundle, ["e1", "e2"])
    record = materialize_sft_records({"bundle-a": bundle}, [case])[0]

    errors = validate_sft_record_budget(record, case, max_seq_length=1)

    assert any("exceed max_seq_length" in error for error in errors)


def _bundle(
    bundle_id: str,
    thread_key: str,
    evidence_ids: list[str],
    *,
    repo: str = "acme/project",
) -> dict:
    return {
        "bundle_id": bundle_id,
        "repo": repo,
        "thread_key": thread_key,
        "question": "Why was auth kept synchronous?",
        "evidence": [
            {
                "evidence_id": evidence_id,
                "kind": "pull",
                "source_id": evidence_id,
                "summary": f"Evidence {evidence_id}",
            }
            for evidence_id in evidence_ids
        ],
    }


def _case(bundle: dict, citations: list[str]) -> dict:
    return {
        "bundle_id": bundle["bundle_id"],
        "question": "Why was auth kept synchronous?",
        "answer": "The evidence suggests ordering risk, but context is incomplete.",
        "facts": [{"text": "The PR discussed auth ordering.", "citations": citations[:1]}],
        "timeline": [
            {"date": "2026-01-01T00:00:00Z", "text": "Discussion", "citations": citations[:1]},
        ],
        "inference": "The implementation likely avoided refresh races.",
        "uncertainty": "Offline discussion and later reversions are not available.",
        "citations": citations,
        "review_status": "approved",
        "reviewer_id": "reviewer-1",
        "reviewed_at": "2026-01-02T00:00:00Z",
        "review_revision": "1",
        "bundle_hash": bundle_hash(bundle),
        "evidence_hash": evidence_hash(bundle),
    }
