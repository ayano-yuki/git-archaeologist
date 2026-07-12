import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from llm_tuning_lab.train import dpo
from llm_tuning_lab.train.dpo_runtime import validate_dpo_inputs
from llm_tuning_lab.train.manifest import training_manifest_hash, write_training_manifest


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


def test_training_manifest_records_lora_and_dpo_parent_lineage(tmp_path: Path) -> None:
    train_file = tmp_path / "dpo.jsonl"
    output_dir = tmp_path / "manifest"
    train_file.write_text('{"prompt":"p","chosen":"good","rejected":"bad"}\n', encoding="utf-8")

    path = write_training_manifest(
        output_dir,
        model_config={"model_name_or_path": "base-model"},
        data_config={"train_file": str(train_file)},
        train_config={
            "output_dir": str(output_dir),
            "per_device_train_batch_size": 2,
            "gradient_accumulation_steps": 3,
        },
        lora_config={"r": 8},
        parent_sft_adapter="outputs/sft",
        parent_manifest_hash=None,
    )

    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["manifest_schema_version"] == 2
    assert manifest["lora_config"] == {"r": 8}
    assert manifest["parent_sft_adapter"] == "outputs/sft"
    assert manifest["parent_manifest_hash"] is None
    assert manifest["effective_batch_size"] == 6


def test_training_manifest_hash_returns_parent_manifest_digest(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    manifest = adapter_dir / "training_manifest.json"
    manifest.write_text('{"manifest_schema_version":2}\n', encoding="utf-8")

    assert training_manifest_hash(adapter_dir) == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert training_manifest_hash(tmp_path / "missing") is None


def test_run_dpo_uses_sft_adapter_for_policy_and_reference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    train_file = tmp_path / "dpo.jsonl"
    output_dir = tmp_path / "dpo"
    adapter_dir = tmp_path / "sft_adapter"
    adapter_dir.mkdir()
    parent_manifest = adapter_dir / "training_manifest.json"
    parent_manifest.write_text('{"parent":"sft"}\n', encoding="utf-8")
    train_file.write_text('{"prompt":"p","chosen":"good","rejected":"bad"}\n', encoding="utf-8")

    class AutoPeftModelForCausalLM:
        calls: list[tuple[str, dict]] = []

        @classmethod
        def from_pretrained(cls, adapter_input: str, **kwargs: object) -> dict[str, object]:
            cls.calls.append((adapter_input, kwargs))
            return {"adapter_input": adapter_input, **kwargs}

    class AutoModelForCausalLM:
        calls: list[tuple[str, dict]] = []

        @classmethod
        def from_pretrained(cls, model_name: str, **kwargs: object) -> dict[str, object]:
            cls.calls.append((model_name, kwargs))
            return {"model_name": model_name, **kwargs}

    class AutoTokenizer:
        @classmethod
        def from_pretrained(cls, *_args: object, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(pad_token=None, eos_token="<eos>")

    class DPOTrainer:
        init_kwargs: dict | None = None

        def __init__(self, **kwargs: object) -> None:
            type(self).init_kwargs = dict(kwargs)

        def train(self) -> None:
            pass

        def save_model(self, output: str) -> None:
            assert output == str(output_dir)

    monkeypatch.setattr(
        dpo,
        "load_dpo_dependencies",
        lambda: {
            "AutoModelForCausalLM": AutoModelForCausalLM,
            "AutoPeftModelForCausalLM": AutoPeftModelForCausalLM,
            "AutoTokenizer": AutoTokenizer,
            "BitsAndBytesConfig": object,
            "DPOConfig": lambda **kwargs: kwargs,
            "DPOTrainer": DPOTrainer,
            "LoraConfig": lambda **kwargs: {"lora": kwargs},
            "load_dataset": lambda *_args, **_kwargs: {"train": ["row"]},
            "torch": SimpleNamespace(),
        },
    )

    dpo.run_dpo(
        model_config={"model_name_or_path": "base-model"},
        data_config={"train_file": str(train_file)},
        train_config={"output_dir": str(output_dir)},
        lora_config={"r": 8},
        sft_adapter_path=str(adapter_dir),
    )

    assert AutoModelForCausalLM.calls == []
    assert AutoPeftModelForCausalLM.calls == [
        (str(adapter_dir), {"is_trainable": True, "trust_remote_code": False}),
        (str(adapter_dir), {"is_trainable": False, "trust_remote_code": False}),
    ]
    assert DPOTrainer.init_kwargs is not None
    assert "peft_config" not in DPOTrainer.init_kwargs
    assert DPOTrainer.init_kwargs["model"]["is_trainable"] is True
    assert DPOTrainer.init_kwargs["ref_model"]["is_trainable"] is False

    manifest = json.loads((output_dir / "training_manifest.json").read_text(encoding="utf-8"))
    assert manifest["parent_sft_adapter"] == str(adapter_dir)
    assert manifest["parent_manifest_hash"] == hashlib.sha256(parent_manifest.read_bytes()).hexdigest()
