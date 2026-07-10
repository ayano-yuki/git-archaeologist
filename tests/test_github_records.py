from pathlib import Path

from llm_tuning_lab.collect.github_records import wrap_github_record, write_jsonl


def test_wrap_github_record_keeps_source_metadata() -> None:
    record = wrap_github_record(
        "react/react",
        "issue",
        {"id": 1, "number": 42, "html_url": "https://github.com/react/react/issues/42"},
    )

    assert record["source"] == "github"
    assert record["repo"] == "react/react"
    assert record["kind"] == "issue"
    assert record["github_id"] == 1
    assert record["number"] == 42


def test_write_jsonl_returns_count(tmp_path: Path) -> None:
    output = tmp_path / "records.jsonl"

    count = write_jsonl(output, [{"a": 1}, {"a": 2}])

    assert count == 2
    assert output.read_text(encoding="utf-8").count("\n") == 2
