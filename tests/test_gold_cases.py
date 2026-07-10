from llm_tuning_lab.data.gold_cases import (
    materialize_sft_records,
    split_gold_cases,
    validate_gold_cases,
)


def test_gold_case_validation_rejects_invented_citation() -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    case = _case("bundle-a", ["e1", "missing"])

    result = validate_gold_cases({"bundle-a": bundle}, [case])

    assert not result.ok
    assert any("citations not found" in error for error in result.errors)


def test_gold_case_validation_rejects_missing_fact_citation() -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    case = _case("bundle-a", ["e1", "e2"])
    case["facts"] = [{"text": "The PR kept sync auth."}]

    result = validate_gold_cases({"bundle-a": bundle}, [case])

    assert not result.ok
    assert any("must cite evidence" in error for error in result.errors)


def test_gold_case_validation_rejects_malformed_timeline() -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    case = _case("bundle-a", ["e1", "e2"])
    case["timeline"] = [
        {"date": "2026-02-01T00:00:00Z", "text": "Second", "citations": ["e2"]},
        {"date": "2026-01-01T00:00:00Z", "text": "First", "citations": ["e1"]},
    ]

    result = validate_gold_cases({"bundle-a": bundle}, [case])

    assert not result.ok
    assert any("chronological" in error for error in result.errors)


def test_materialize_sft_records_only_includes_approved_cases() -> None:
    bundles = {"bundle-a": _bundle("bundle-a", "pull:1", ["e1", "e2"])}
    approved = _case("bundle-a", ["e1", "e2"])
    draft = _case("bundle-a", ["e1", "e2"])
    draft["review_status"] = "draft"

    records = materialize_sft_records(bundles, [approved, draft])

    assert len(records) == 1
    assert records[0]["messages"][0]["role"] == "system"
    assert "Evidence:" in records[0]["messages"][1]["content"]


def test_thread_hash_split_keeps_same_thread_in_one_split() -> None:
    bundles = {
        "bundle-a": _bundle("bundle-a", "pull:1", ["e1", "e2"]),
        "bundle-b": _bundle("bundle-b", "pull:1", ["e3", "e4"]),
    }
    cases = [_case("bundle-a", ["e1", "e2"]), _case("bundle-b", ["e3", "e4"])]

    splits = split_gold_cases(bundles, cases, validation_ratio=0.4, test_ratio=0.4)
    locations = [name for name, split_cases in splits.items() if split_cases for _ in split_cases]

    assert len(set(locations)) == 1


def _bundle(bundle_id: str, thread_key: str, evidence_ids: list[str]) -> dict:
    return {
        "bundle_id": bundle_id,
        "repo": "acme/project",
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


def _case(bundle_id: str, citations: list[str]) -> dict:
    return {
        "bundle_id": bundle_id,
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
    }
