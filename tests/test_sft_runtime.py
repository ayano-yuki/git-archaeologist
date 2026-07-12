from pathlib import Path
from types import SimpleNamespace

import pytest

from llm_tuning_lab.train import sft
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


def test_run_sft_uses_trainable_adapter_input(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    train_file = tmp_path / "train.jsonl"
    output_dir = tmp_path / "sft"
    train_file.write_text(
        '{"messages":[{"role":"user","content":"u"},{"role":"assistant","content":"a"}]}\n',
        encoding="utf-8",
    )

    class AutoPeftModelForCausalLM:
        calls: list[tuple[str, dict]] = []

        @classmethod
        def from_pretrained(cls, adapter_input: str, **kwargs: object) -> dict[str, object]:
            cls.calls.append((adapter_input, kwargs))
            return {"adapter_input": adapter_input, **kwargs}

    class SFTTrainer:
        init_kwargs: dict | None = None

        def __init__(self, **kwargs: object) -> None:
            type(self).init_kwargs = dict(kwargs)

        def train(self) -> None:
            pass

        def save_model(self, output: str) -> None:
            assert output == str(output_dir)

    def fail_lora_config(**_kwargs: object) -> object:
        raise AssertionError("adapter continuation should not create a new LoRA config")

    monkeypatch.setattr(
        sft,
        "load_training_dependencies",
        lambda: {
            "AutoPeftModelForCausalLM": AutoPeftModelForCausalLM,
            "BitsAndBytesConfig": object,
            "LoraConfig": fail_lora_config,
            "SFTConfig": lambda **kwargs: kwargs,
            "SFTTrainer": SFTTrainer,
            "load_dataset": lambda *_args, **_kwargs: {"train": ["row"]},
            "torch": SimpleNamespace(),
        },
    )

    sft.run_sft(
        model_config={"model_name_or_path": "base-model", "trust_remote_code": True},
        data_config={"train_file": str(train_file)},
        train_config={"output_dir": str(output_dir)},
        lora_config={"r": 8},
        adapter_input="outputs/sft-adapter",
    )

    assert AutoPeftModelForCausalLM.calls == [
        ("outputs/sft-adapter", {"is_trainable": True, "trust_remote_code": True})
    ]
    assert SFTTrainer.init_kwargs is not None
    assert SFTTrainer.init_kwargs["model"] == {
        "adapter_input": "outputs/sft-adapter",
        "is_trainable": True,
        "trust_remote_code": True,
    }
    assert "peft_config" not in SFTTrainer.init_kwargs


def test_run_sft_without_adapter_keeps_base_model_lora_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    train_file = tmp_path / "train.jsonl"
    output_dir = tmp_path / "sft"
    train_file.write_text(
        '{"messages":[{"role":"user","content":"u"},{"role":"assistant","content":"a"}]}\n',
        encoding="utf-8",
    )

    class SFTTrainer:
        init_kwargs: dict | None = None

        def __init__(self, **kwargs: object) -> None:
            type(self).init_kwargs = dict(kwargs)

        def train(self) -> None:
            pass

        def save_model(self, output: str) -> None:
            assert output == str(output_dir)

    monkeypatch.setattr(
        sft,
        "load_training_dependencies",
        lambda: {
            "AutoPeftModelForCausalLM": object,
            "BitsAndBytesConfig": object,
            "LoraConfig": lambda **kwargs: {"lora": kwargs},
            "SFTConfig": lambda **kwargs: kwargs,
            "SFTTrainer": SFTTrainer,
            "load_dataset": lambda *_args, **_kwargs: {"train": ["row"]},
            "torch": SimpleNamespace(),
        },
    )

    sft.run_sft(
        model_config={"model_name_or_path": "base-model"},
        data_config={"train_file": str(train_file)},
        train_config={"output_dir": str(output_dir)},
        lora_config={"r": 8},
    )

    assert SFTTrainer.init_kwargs is not None
    assert SFTTrainer.init_kwargs["model"] == "base-model"
    assert SFTTrainer.init_kwargs["peft_config"] == {"lora": {"r": 8}}
