import json
import sys
from pathlib import Path

import pytest

from llm_tuning_lab.data.bundles import write_jsonl
from llm_tuning_lab.data.gold_cases import bundle_hash, evidence_hash
from llm_tuning_lab.data.roadmap import (
    SYSTEM_PROMPT,
    main,
    materialize_dpo_records,
    materialize_raft_records,
)


def test_raft_records_include_distractors_but_answer_cites_gold_evidence() -> None:
    bundles = {
        "bundle-a": _bundle("bundle-a", "pull:1", ["e1", "e2"]),
        "bundle-b": _bundle("bundle-b", "pull:2", ["d1", "d2"]),
    }
    case = _case(bundles["bundle-a"], ["e1", "e2"])

    records = materialize_raft_records(bundles, [case], distractors_per_record=1)

    assert len(records) == 1
    user_content = records[0]["messages"][1]["content"]
    assistant = json.loads(records[0]["messages"][2]["content"])
    assert "Some items may be irrelevant" in user_content
    assert "e1" in user_content
    assert "d" in user_content
    assert assistant["citations"] == ["e1", "e2"]


def test_roadmap_materializers_skip_unapproved_cases() -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    approved = _case(bundle, ["e1"])
    draft = _case(bundle, ["e2"])
    draft["review_status"] = "draft"

    records = materialize_dpo_records({"bundle-a": bundle}, [approved, draft])

    assert len(records) == 1
    assert records[0]["chosen"] != records[0]["rejected"]
    assert "definitely" in records[0]["rejected"]


def test_dpo_prompt_preserves_system_instruction_as_string() -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    case = _case(bundle, ["e1"])

    records = materialize_dpo_records({"bundle-a": bundle}, [case])

    assert set(records[0]) == {"prompt", "chosen", "rejected"}
    assert isinstance(records[0]["prompt"], str)
    assert records[0]["prompt"].startswith(f"System: {SYSTEM_PROMPT}\n\nUser:\n")
    assert "Repository: acme/project" in records[0]["prompt"]


def test_split_outputs_reject_empty_validation_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle("bundle-a", "pull:1", ["e1", "e2"])
    bundles_path = tmp_path / "bundles.jsonl"
    cases_path = tmp_path / "gold_cases.jsonl"
    train_output = tmp_path / "train.jsonl"
    validation_output = tmp_path / "validation.jsonl"
    write_jsonl(bundles_path, [bundle])
    write_jsonl(cases_path, [_case(bundle, ["e1"])])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "roadmap",
            "dpo",
            "--bundles",
            str(bundles_path),
            "--gold-cases",
            str(cases_path),
            "--train-output",
            str(train_output),
            "--validation-output",
            str(validation_output),
        ],
    )

    with pytest.raises(ValueError, match="non-empty validation split"):
        main()

    assert not train_output.exists()
    assert not validation_output.exists()


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
