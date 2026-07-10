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


def load_training_dependencies() -> dict[str, Any]:
    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from transformers import TrainingArguments
        from trl import SFTTrainer
    except ImportError as exc:
        raise RuntimeError(
            "Training dependencies are missing. Install them with: "
            "uv sync --system-certs --extra train --group dev"
        ) from exc

    return {
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "BitsAndBytesConfig": BitsAndBytesConfig,
        "LoraConfig": LoraConfig,
        "SFTTrainer": SFTTrainer,
        "TrainingArguments": TrainingArguments,
        "load_dataset": load_dataset,
        "torch": torch,
    }


def torch_dtype(torch_module: Any, name: str | None) -> Any:
    if not name:
        return None
    return getattr(torch_module, name)


def render_chat_dataset(dataset: Any, tokenizer: Any) -> Any:
    def render_record(record: dict[str, Any]) -> dict[str, str]:
        return {
            "text": tokenizer.apply_chat_template(
                record["messages"],
                tokenize=False,
                add_generation_prompt=False,
            )
        }

    return dataset.map(render_record)


def path_exists(path_value: str | None) -> bool:
    return bool(path_value and Path(path_value).exists())
