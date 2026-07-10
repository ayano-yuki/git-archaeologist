from pathlib import Path

import pytest

from llm_tuning_lab.train.sft_runtime import build_data_files, validate_sft_inputs


def test_build_data_files_with_train_only() -> None:
    data_files = build_data_files({"train_file": "data/samples/sft_sample.jsonl"})

    assert data_files == {"train": "data/samples/sft_sample.jsonl"}


def test_build_data_files_with_validation() -> None:
    data_files = build_data_files(
        {
            "train_file": "data/processed/train.jsonl",
            "validation_file": "data/processed/validation.jsonl",
        }
    )

    assert data_files == {
        "train": "data/processed/train.jsonl",
        "validation": "data/processed/validation.jsonl",
    }


def test_validate_sft_inputs_checks_missing_train_file() -> None:
    with pytest.raises(FileNotFoundError, match="train_file does not exist"):
        validate_sft_inputs(
            {"model_name_or_path": "Qwen/Qwen3-14B"},
            {"train_file": "missing.jsonl"},
            {"output_dir": "outputs/sft"},
        )


def test_validate_sft_inputs_accepts_existing_files(tmp_path: Path) -> None:
    train_file = tmp_path / "train.jsonl"
    train_file.write_text(
        '{"messages":[{"role":"user","content":"u"},{"role":"assistant","content":"a"}]}\n',
        encoding="utf-8",
    )

    validate_sft_inputs(
        {"model_name_or_path": "Qwen/Qwen3-14B"},
        {"train_file": str(train_file)},
        {"output_dir": "outputs/sft"},
    )


def test_validate_sft_inputs_rejects_empty_train_file(tmp_path: Path) -> None:
    train_file = tmp_path / "train.jsonl"
    train_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain at least one JSONL record"):
        validate_sft_inputs(
            {"model_name_or_path": "Qwen/Qwen3-14B"},
            {"train_file": str(train_file)},
            {"output_dir": "outputs/sft"},
        )


def test_validate_sft_inputs_rejects_empty_validation_file(tmp_path: Path) -> None:
    train_file = tmp_path / "train.jsonl"
    validation_file = tmp_path / "validation.jsonl"
    train_file.write_text(
        '{"messages":[{"role":"user","content":"u"},{"role":"assistant","content":"a"}]}\n',
        encoding="utf-8",
    )
    validation_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="validation_file must contain"):
        validate_sft_inputs(
            {"model_name_or_path": "Qwen/Qwen3-14B"},
            {"train_file": str(train_file), "validation_file": str(validation_file)},
            {"output_dir": "outputs/sft"},
        )
