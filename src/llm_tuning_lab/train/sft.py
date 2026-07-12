from __future__ import annotations

import argparse
from pathlib import Path

from llm_tuning_lab.config import load_yaml, override_if_set
from llm_tuning_lab.train.accounting import compute_jsonl_accounting
from llm_tuning_lab.train.manifest import write_training_manifest
from llm_tuning_lab.train.sft_runtime import (
    build_data_files,
    load_training_dependencies,
    torch_dtype,
    validate_sft_inputs,
)


def run_sft(
    model_config: dict,
    data_config: dict,
    train_config: dict,
    lora_config: dict,
    adapter_input: str | None = None,
) -> None:
    validate_sft_inputs(model_config, data_config, train_config)
    deps = load_training_dependencies()
    torch = deps["torch"]

    model_init_kwargs = {
        "trust_remote_code": model_config.get("trust_remote_code", False),
    }
    dtype = torch_dtype(torch, model_config.get("torch_dtype"))
    if dtype is not None:
        model_init_kwargs["torch_dtype"] = dtype
    if model_config.get("device_map"):
        model_init_kwargs["device_map"] = model_config["device_map"]
    if model_config.get("attn_implementation"):
        model_init_kwargs["attn_implementation"] = model_config["attn_implementation"]

    quantization_config = None
    if model_config.get("load_in_4bit"):
        quantization_config = deps["BitsAndBytesConfig"](
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch_dtype(torch, model_config.get("torch_dtype")),
            bnb_4bit_quant_type="nf4",
        )
        model_init_kwargs["quantization_config"] = quantization_config

    dataset = deps["load_dataset"]("json", data_files=build_data_files(data_config))

    training_arg_kwargs = {
        "output_dir": train_config.get("output_dir", "outputs/sft"),
        "num_train_epochs": train_config.get("num_train_epochs", 1),
        "per_device_train_batch_size": train_config.get("per_device_train_batch_size", 1),
        "gradient_accumulation_steps": train_config.get("gradient_accumulation_steps", 1),
        "learning_rate": train_config.get("learning_rate", 0.0002),
        "warmup_ratio": train_config.get("warmup_ratio", 0.0),
        "logging_steps": train_config.get("logging_steps", 10),
        "save_steps": train_config.get("save_steps", 100),
        "bf16": train_config.get("bf16", False),
        "seed": train_config.get("seed", 42),
        "max_length": train_config.get("max_seq_length", 2048),
        "assistant_only_loss": train_config.get("assistant_only_loss", True),
        "packing": train_config.get("packing", False),
        "gradient_checkpointing": train_config.get("gradient_checkpointing", True),
        "eos_token": train_config.get("eos_token"),
        "model_init_kwargs": model_init_kwargs,
    }
    for optional_key in ("max_steps", "eval_steps", "save_total_limit"):
        if train_config.get(optional_key) is not None:
            training_arg_kwargs[optional_key] = train_config[optional_key]
    training_args = deps["SFTConfig"](**training_arg_kwargs)

    trainer_kwargs = {
        "args": training_args,
        "train_dataset": dataset["train"],
        "eval_dataset": dataset.get("validation"),
    }
    if adapter_input:
        trainer_kwargs["model"] = deps["AutoPeftModelForCausalLM"].from_pretrained(
            adapter_input,
            is_trainable=True,
            **model_init_kwargs,
        )
    else:
        trainer_kwargs["model"] = model_config["model_name_or_path"]
        trainer_kwargs["peft_config"] = deps["LoraConfig"](**lora_config)

    trainer = deps["SFTTrainer"](**trainer_kwargs)
    trainer.train()
    trainer.save_model(train_config.get("output_dir", "outputs/sft"))
    write_training_manifest(
        Path(str(train_config.get("output_dir", "outputs/sft"))),
        model_config=model_config,
        data_config=data_config,
        train_config=train_config,
        lora_config=None if adapter_input else lora_config,
        accounting=_training_accounting(data_config, train_config),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run supervised fine-tuning.")
    parser.add_argument("--model-config", type=Path, default=Path("configs/model/base.yaml"))
    parser.add_argument("--data-config", type=Path, default=Path("configs/data/sft.yaml"))
    parser.add_argument("--train-config", type=Path, default=Path("configs/train/sft.yaml"))
    parser.add_argument("--lora-config", type=Path, default=Path("configs/train/lora.yaml"))
    parser.add_argument("--train-file", type=str, help="Override train_file from data config.")
    parser.add_argument("--validation-file", type=str, help="Override validation_file from data config.")
    parser.add_argument("--output-dir", type=str, help="Override output_dir from train config.")
    parser.add_argument(
        "--adapter-input",
        type=str,
        help="Continue SFT from an existing PEFT adapter directory.",
    )
    parser.add_argument("--preflight-only", action="store_true", help="Validate configs and data without training.")
    args = parser.parse_args()

    data_config = load_yaml(args.data_config)
    train_config = load_yaml(args.train_config)
    override_if_set(data_config, "train_file", args.train_file)
    override_if_set(data_config, "validation_file", args.validation_file)
    override_if_set(train_config, "output_dir", args.output_dir)
    model_config = load_yaml(args.model_config)

    if args.preflight_only:
        validate_sft_inputs(model_config, data_config, train_config)
        print("OK: SFT configs and data files are ready.")
        return 0

    run_sft(
        model_config=model_config,
        data_config=data_config,
        train_config=train_config,
        lora_config=load_yaml(args.lora_config),
        adapter_input=args.adapter_input,
    )
    return 0


def _training_accounting(data_config: dict, train_config: dict) -> dict:
    max_seq_length = int(train_config.get("max_seq_length", 2048))
    common = {
        "max_seq_length": max_seq_length,
        "per_device_train_batch_size": int(train_config.get("per_device_train_batch_size", 1)),
        "gradient_accumulation_steps": int(train_config.get("gradient_accumulation_steps", 1)),
        "max_steps": train_config.get("max_steps"),
        "num_train_epochs": int(train_config.get("num_train_epochs", 1)),
        "packing": bool(train_config.get("packing", False)),
    }
    accounting = {
        "train": compute_jsonl_accounting(Path(str(data_config["train_file"])), **common).as_dict()
    }
    validation_file = data_config.get("validation_file")
    if validation_file:
        accounting["validation"] = compute_jsonl_accounting(
            Path(str(validation_file)), **common
        ).as_dict()
    else:
        accounting["validation"] = None
    return accounting


if __name__ == "__main__":
    raise SystemExit(main())
