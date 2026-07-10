import json
from pathlib import Path

from llm_tuning_lab.data.github_sft import (
    build_sft_records,
    load_github_records,
    split_train_validation,
    write_sft_jsonl,
)
from llm_tuning_lab.data.validate import validate_jsonl


def test_prepare_github_records_writes_valid_messages_jsonl(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_record = {
        "source": "github",
        "repo": "react/react",
        "kind": "issue",
        "github_id": 1,
        "number": 42,
        "data": {
            "id": 1,
            "number": 42,
            "title": "Clarify React docs wording",
            "state": "closed",
            "body": "The issue asks why the wording changed.",
            "user": {"login": "maintainer"},
        },
    }
    (raw_dir / "issues.jsonl").write_text(
        json.dumps(raw_record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    records = build_sft_records(load_github_records(raw_dir))
    train_records, validation_records = split_train_validation(records * 2, 0.5)
    train_path = tmp_path / "train.jsonl"
    validation_path = tmp_path / "validation.jsonl"

    assert write_sft_jsonl(train_path, train_records) == 1
    assert write_sft_jsonl(validation_path, validation_records) == 1
    assert validate_jsonl(train_path) == []
    assert validate_jsonl(validation_path) == []


def test_split_train_validation_keeps_train_non_empty() -> None:
    records = [{"messages": [{"role": "user", "content": "u"}, {"role": "assistant", "content": "a"}]}]

    train_records, validation_records = split_train_validation(records, 0.2)

    assert train_records == records
    assert validation_records == []
