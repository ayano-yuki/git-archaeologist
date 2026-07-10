from __future__ import annotations

import argparse
from pathlib import Path

from llm_tuning_lab.config import load_yaml, override_if_set
from llm_tuning_lab.train.sft_runtime import (
    build_data_files,
    load_training_dependencies,
    render_chat_dataset,
    torch_dtype,
)


def run_sft(
    model_config: dict,
    data_config: dict,
    train_config: dict,
    lora_config: dict,
) -> None:
    deps = load_training_dependencies()
    torch = deps["torch"]

    tokenizer = deps["AutoTokenizer"].from_pretrained(
        model_config["model_name_or_path"],
        trust_remote_code=model_config.get("trust_remote_code", False),
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quantization_config = None
    if model_config.get("load_in_4bit"):
        quantization_config = deps["BitsAndBytesConfig"](
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch_dtype(torch, model_config.get("torch_dtype")),
            bnb_4bit_quant_type="nf4",
        )

    model = deps["AutoModelForCausalLM"].from_pretrained(
        model_config["model_name_or_path"],
        trust_remote_code=model_config.get("trust_remote_code", False),
        torch_dtype=torch_dtype(torch, model_config.get("torch_dtype")),
        quantization_config=quantization_config,
    )

    dataset = deps["load_dataset"]("json", data_files=build_data_files(data_config))
    dataset = render_chat_dataset(dataset, tokenizer)

    training_args = deps["TrainingArguments"](
        output_dir=train_config.get("output_dir", "outputs/sft"),
        num_train_epochs=train_config.get("num_train_epochs", 1),
        per_device_train_batch_size=train_config.get("per_device_train_batch_size", 1),
        gradient_accumulation_steps=train_config.get("gradient_accumulation_steps", 1),
        learning_rate=train_config.get("learning_rate", 0.0002),
        warmup_ratio=train_config.get("warmup_ratio", 0.0),
        logging_steps=train_config.get("logging_steps", 10),
        save_steps=train_config.get("save_steps", 100),
        bf16=train_config.get("bf16", False),
    )

    trainer = deps["SFTTrainer"](
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset.get("validation"),
        peft_config=deps["LoraConfig"](**lora_config),
        dataset_text_field="text",
        max_seq_length=train_config.get("max_seq_length", 2048),
    )
    trainer.train()
    trainer.save_model(train_config.get("output_dir", "outputs/sft"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run supervised fine-tuning.")
    parser.add_argument("--model-config", type=Path, default=Path("configs/model/base.yaml"))
    parser.add_argument("--data-config", type=Path, default=Path("configs/data/sft.yaml"))
    parser.add_argument("--train-config", type=Path, default=Path("configs/train/sft.yaml"))
    parser.add_argument("--lora-config", type=Path, default=Path("configs/train/lora.yaml"))
    parser.add_argument("--train-file", type=str, help="Override train_file from data config.")
    parser.add_argument("--validation-file", type=str, help="Override validation_file from data config.")
    args = parser.parse_args()

    data_config = load_yaml(args.data_config)
    override_if_set(data_config, "train_file", args.train_file)
    override_if_set(data_config, "validation_file", args.validation_file)

    run_sft(
        model_config=load_yaml(args.model_config),
        data_config=data_config,
        train_config=load_yaml(args.train_config),
        lora_config=load_yaml(args.lora_config),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
