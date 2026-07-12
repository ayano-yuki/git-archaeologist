from pathlib import Path

import pytest

from llm_tuning_lab.train.dpo_runtime import validate_dpo_inputs


def test_validate_dpo_inputs_accepts_preference_file(tmp_path: Path) -> None:
    train_file = tmp_path / "dpo.jsonl"
    train_file.write_text(
        '{"prompt":"p","chosen":"good","rejected":"bad"}\n',
        encoding="utf-8",
    )

    validate_dpo_inputs(
        {"model_name_or_path": "Qwen/Qwen3-14B"},
        {"train_file": str(train_file)},
        {"output_dir": "outputs/dpo"},
    )


def test_validate_dpo_inputs_rejects_messages_file(tmp_path: Path) -> None:
    train_file = tmp_path / "messages.jsonl"
    train_file.write_text(
        '{"messages":[{"role":"user","content":"u"},{"role":"assistant","content":"a"}]}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="prompt must be a non-empty string"):
        validate_dpo_inputs(
            {"model_name_or_path": "Qwen/Qwen3-14B"},
            {"train_file": str(train_file)},
            {"output_dir": "outputs/dpo"},
        )
