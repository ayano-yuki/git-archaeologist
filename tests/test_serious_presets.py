from pathlib import Path

from llm_tuning_lab.config import load_yaml


def test_h100_overnight_train_preset_invariants() -> None:
    train = load_yaml(Path("configs/train/sft_h100_overnight.yaml"))
    lora = load_yaml(Path("configs/train/lora_h100_overnight.yaml"))
    dpo = load_yaml(Path("configs/train/dpo_h100_overnight.yaml"))

    assert train["max_steps"] == 2000
    assert train["max_seq_length"] == 4096
    assert train["packing"] is True
    assert train["gradient_accumulation_steps"] == 16
    assert train["learning_rate"] == 0.0001
    assert train["eval_steps"] == 100
    assert train["save_steps"] == 250
    assert train["save_total_limit"] == 4
    assert train["bf16"] is True
    assert train["assistant_only_loss"] is True
    assert lora["r"] == 64
    assert lora["lora_alpha"] == 128
    assert lora["target_modules"] == [
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ]
    assert dpo["max_steps"] == 1000
    assert dpo["max_length"] == 4096
    assert dpo["max_prompt_length"] == 2048
    assert dpo["gradient_accumulation_steps"] == 16
    assert dpo["eval_steps"] == 100
    assert dpo["save_total_limit"] == 4


def test_serious_model_profiles_and_run_preset() -> None:
    top = load_yaml(Path("configs/model/top.yaml"))
    h100 = load_yaml(Path("configs/model/h100_80gb.yaml"))
    fallback = load_yaml(Path("configs/model/fallback_shared.yaml"))
    run = load_yaml(Path("configs/run/react_react_h100_overnight.yaml"))

    assert top["model_name_or_path"] == "Qwen/Qwen3-Coder-480B-A35B-Instruct"
    assert top["model_tier"] == "top"
    assert h100["model_name_or_path"] == "Qwen/Qwen2.5-Coder-32B-Instruct"
    assert h100["model_tier"] == "h100_80gb"
    assert fallback["model_name_or_path"] == "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    assert fallback["model_tier"] == "fallback_shared"
    assert run["model_config"] == "configs/model/h100_80gb.yaml"
    assert run["train_config"] == "configs/train/sft_h100_overnight.yaml"
    assert run["lora_config"] == "configs/train/lora_h100_overnight.yaml"
    assert run["dpo_train_config"] == "configs/train/dpo_h100_overnight.yaml"
    assert run["gpu_vram_gb"] == 80
    assert run["gpu_mode"] == "h100_80gb"
    assert run["model_tier"] == "h100_80gb"
    assert run["min_approved_gold_cases"] == 1000
    assert run["min_train_target_tokens"] == 1000000
    assert run["strict_eval"] is True
