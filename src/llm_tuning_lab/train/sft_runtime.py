from __future__ import annotations

from pathlib import Path
from typing import Any


def build_data_files(data_config: dict[str, Any]) -> dict[str, str]:
    train_file = data_config.get("train_file")
    validation_file = data_config.get("validation_file")

    if not train_file:
        raise ValueError("data config must define train_file")

    data_files = {"train": str(train_file)}
    if validation_file:
        data_files["validation"] = str(validation_file)

    return data_files


def validate_sft_inputs(
    model_config: dict[str, Any],
    data_config: dict[str, Any],
    train_config: dict[str, Any],
) -> None:
    if not model_config.get("model_name_or_path"):
        raise ValueError("model config must define model_name_or_path")
    if not data_config.get("train_file"):
        raise ValueError("data config must define train_file")
    _validate_nonempty_jsonl(Path(str(data_config["train_file"])), "train_file")
    validation_file = data_config.get("validation_file")
    if validation_file:
        _validate_nonempty_jsonl(Path(str(validation_file)), "validation_file")
    if not train_config.get("output_dir"):
        raise ValueError("train config must define output_dir")


def load_training_dependencies() -> dict[str, Any]:
    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import BitsAndBytesConfig
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise RuntimeError(
            "Training dependencies are missing. Install them with: "
            "uv sync --system-certs --extra train --group dev"
        ) from exc

    return {
        "BitsAndBytesConfig": BitsAndBytesConfig,
        "LoraConfig": LoraConfig,
        "SFTConfig": SFTConfig,
        "SFTTrainer": SFTTrainer,
        "load_dataset": load_dataset,
        "torch": torch,
    }


def torch_dtype(torch_module: Any, name: str | None) -> Any:
    if not name:
        return None
    return getattr(torch_module, name)


def _validate_nonempty_jsonl(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{label} must be a file: {path}")
    with path.open(encoding="utf-8") as handle:
        if not any(line.strip() for line in handle):
            raise ValueError(f"{label} must contain at least one JSONL record: {path}")
