from __future__ import annotations

from pathlib import Path
from typing import Any

from llm_tuning_lab.data.validate import validate_jsonl
from llm_tuning_lab.train.sft_runtime import build_data_files, torch_dtype


def validate_dpo_inputs(
    model_config: dict[str, Any],
    data_config: dict[str, Any],
    train_config: dict[str, Any],
) -> None:
    if not model_config.get("model_name_or_path"):
        raise ValueError("model config must define model_name_or_path")
    if not data_config.get("train_file"):
        raise ValueError("data config must define train_file")
    _validate_preference_jsonl(Path(str(data_config["train_file"])), "train_file")
    validation_file = data_config.get("validation_file")
    if validation_file:
        _validate_preference_jsonl(Path(str(validation_file)), "validation_file")
    if not train_config.get("output_dir"):
        raise ValueError("train config must define output_dir")


def load_dpo_dependencies() -> dict[str, Any]:
    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from trl import DPOConfig, DPOTrainer
    except ImportError as exc:
        raise RuntimeError(
            "Training dependencies are missing. Install them with: "
            "uv sync --system-certs --extra train --group dev"
        ) from exc

    return {
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "BitsAndBytesConfig": BitsAndBytesConfig,
        "DPOConfig": DPOConfig,
        "DPOTrainer": DPOTrainer,
        "LoraConfig": LoraConfig,
        "load_dataset": load_dataset,
        "torch": torch,
    }


def build_model_init_kwargs(model_config: dict[str, Any], deps: dict[str, Any]) -> dict[str, Any]:
    torch = deps["torch"]
    kwargs: dict[str, Any] = {
        "trust_remote_code": model_config.get("trust_remote_code", False),
    }
    dtype = torch_dtype(torch, model_config.get("torch_dtype"))
    if dtype is not None:
        kwargs["torch_dtype"] = dtype
    if model_config.get("device_map"):
        kwargs["device_map"] = model_config["device_map"]
    if model_config.get("attn_implementation"):
        kwargs["attn_implementation"] = model_config["attn_implementation"]
    if model_config.get("load_in_4bit"):
        kwargs["quantization_config"] = deps["BitsAndBytesConfig"](
            load_in_4bit=True,
            bnb_4bit_compute_dtype=dtype,
            bnb_4bit_quant_type="nf4",
        )
    return kwargs


def _validate_preference_jsonl(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{label} must be a file: {path}")
    with path.open(encoding="utf-8") as handle:
        if not any(line.strip() for line in handle):
            raise ValueError(f"{label} must contain at least one JSONL record: {path}")
    errors = validate_jsonl(path, data_format="dpo")
    if errors:
        raise ValueError("; ".join(errors))


__all__ = [
    "build_data_files",
    "build_model_init_kwargs",
    "load_dpo_dependencies",
    "validate_dpo_inputs",
]
