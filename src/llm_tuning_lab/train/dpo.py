from __future__ import annotations

import argparse
from pathlib import Path

from llm_tuning_lab.config import load_yaml, override_if_set
from llm_tuning_lab.train.accounting import compute_jsonl_accounting
from llm_tuning_lab.train.dpo_runtime import (
    build_data_files,
    build_model_init_kwargs,
    load_dpo_dependencies,
    validate_dpo_inputs,
)
from llm_tuning_lab.train.manifest import training_manifest_hash, write_training_manifest


def run_dpo(
    model_config: dict,
    data_config: dict,
    train_config: dict,
    lora_config: dict,
    sft_adapter_path: str | None = None,
) -> None:
    validate_dpo_inputs(model_config, data_config, train_config)
    deps = load_dpo_dependencies()

    tokenizer = deps["AutoTokenizer"].from_pretrained(
        model_config["model_name_or_path"],
        trust_remote_code=model_config.get("trust_remote_code", False),
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_init_kwargs = build_model_init_kwargs(model_config, deps)
    if sft_adapter_path:
        model = deps["AutoPeftModelForCausalLM"].from_pretrained(
            sft_adapter_path,
            is_trainable=True,
            **model_init_kwargs,
        )
        ref_model = deps["AutoPeftModelForCausalLM"].from_pretrained(
            sft_adapter_path,
            is_trainable=False,
            **model_init_kwargs,
        )
        peft_config = None
    else:
        model = deps["AutoModelForCausalLM"].from_pretrained(
            model_config["model_name_or_path"],
            **model_init_kwargs,
        )
        ref_model = None
        peft_config = deps["LoraConfig"](**lora_config)
    dataset = deps["load_dataset"]("json", data_files=build_data_files(data_config))

    training_arg_kwargs = {
        "output_dir": train_config.get("output_dir", "outputs/dpo"),
        "num_train_epochs": train_config.get("num_train_epochs", 1),
        "per_device_train_batch_size": train_config.get("per_device_train_batch_size", 1),
        "gradient_accumulation_steps": train_config.get("gradient_accumulation_steps", 1),
        "learning_rate": train_config.get("learning_rate", 0.00005),
        "beta": train_config.get("beta", 0.1),
        "warmup_ratio": train_config.get("warmup_ratio", 0.0),
        "logging_steps": train_config.get("logging_steps", 10),
        "save_steps": train_config.get("save_steps", 100),
        "bf16": train_config.get("bf16", False),
        "seed": train_config.get("seed", 42),
        "max_length": train_config.get("max_length", 2048),
        "max_prompt_length": train_config.get("max_prompt_length", 1024),
        "gradient_checkpointing": train_config.get("gradient_checkpointing", True),
    }
    for optional_key in ("max_steps", "eval_steps", "save_total_limit"):
        if train_config.get(optional_key) is not None:
            training_arg_kwargs[optional_key] = train_config[optional_key]
    training_args = deps["DPOConfig"](**training_arg_kwargs)

    trainer = deps["DPOTrainer"](
        model=model,
        ref_model=ref_model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset.get("validation"),
        processing_class=tokenizer,
        **({"peft_config": peft_config} if peft_config is not None else {}),
    )
    trainer.train()
    trainer.save_model(train_config.get("output_dir", "outputs/dpo"))
    write_training_manifest(
        Path(str(train_config.get("output_dir", "outputs/dpo"))),
        model_config=model_config,
        data_config=data_config,
        train_config=train_config,
        lora_config=None if sft_adapter_path else lora_config,
        parent_sft_adapter=sft_adapter_path,
        parent_manifest_hash=(
            training_manifest_hash(Path(sft_adapter_path)) if sft_adapter_path else None
        ),
        accounting=_training_accounting(data_config, train_config),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run preference tuning with DPO.")
    parser.add_argument("--model-config", type=Path, default=Path("configs/model/base.yaml"))
    parser.add_argument("--data-config", type=Path, required=True)
    parser.add_argument("--train-config", type=Path, default=Path("configs/train/dpo.yaml"))
    parser.add_argument("--lora-config", type=Path, default=Path("configs/train/lora.yaml"))
    parser.add_argument("--train-file", type=str, help="Override train_file from data config.")
    parser.add_argument("--validation-file", type=str, help="Override validation_file from data config.")
    parser.add_argument("--output-dir", type=str, help="Override output_dir from train config.")
    parser.add_argument(
        "--sft-adapter-path",
        type=str,
        help="Start DPO from an existing SFT PEFT adapter directory.",
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
        validate_dpo_inputs(model_config, data_config, train_config)
        print("OK: DPO configs and preference data files are ready.")
        return 0

    run_dpo(
        model_config=model_config,
        data_config=data_config,
        train_config=train_config,
        lora_config=load_yaml(args.lora_config),
        sft_adapter_path=args.sft_adapter_path,
    )
    return 0


def _training_accounting(data_config: dict, train_config: dict) -> dict:
    max_seq_length = int(train_config.get("max_length", 2048))
    common = {
        "max_seq_length": max_seq_length,
        "per_device_train_batch_size": int(train_config.get("per_device_train_batch_size", 1)),
        "gradient_accumulation_steps": int(train_config.get("gradient_accumulation_steps", 1)),
        "max_steps": train_config.get("max_steps"),
        "num_train_epochs": int(train_config.get("num_train_epochs", 1)),
        "packing": False,
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
