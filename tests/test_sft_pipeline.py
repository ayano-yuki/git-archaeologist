from pathlib import Path

import pytest

from llm_tuning_lab.run.sft_pipeline import (
    PipelineConfig,
    build_commands,
    load_pipeline_config,
    resolve_preset,
)


def test_build_commands_can_skip_collect() -> None:
    config = _pipeline_config()

    commands = build_commands(config, skip_collect=True, insecure_ssl=False)

    assert all("llm_tuning_lab.collect.github" not in command for command in commands)
    assert commands[0][5] == "llm_tuning_lab.data.bundles"
    assert commands[1][5] == "llm_tuning_lab.data.gold_cases"
    assert commands[1][6] == "validate"
    assert commands[2][5] == "llm_tuning_lab.data.gold_cases"
    assert commands[2][6] == "materialize"
    assert "--max-seq-length" in commands[2]
    assert "--split-strategy" in commands[2]
    assert commands[6][5] == "llm_tuning_lab.train.accounting"
    assert commands[7][5] == "llm_tuning_lab.eval.predict"
    assert commands[8][5] == "llm_tuning_lab.eval.run_eval"
    assert commands[-4][5] == "llm_tuning_lab.train.sft"
    assert "--preflight-only" in commands[-4]
    assert commands[-3][5] == "llm_tuning_lab.train.sft"
    assert commands[-2][5] == "llm_tuning_lab.eval.predict"
    assert commands[-1][5] == "llm_tuning_lab.eval.run_eval"


def test_build_commands_adds_prediction_and_strict_eval_gate_flags() -> None:
    config = _pipeline_config(
        copy_expected_predictions=True,
        strict_eval=True,
        min_coverage=1.0,
        min_fact_recall=0.8,
        min_answer_similarity=0.75,
        min_timeline_event_recall=0.6,
    )

    commands = build_commands(config, skip_collect=True, insecure_ssl=False)

    modules = [command[5] for command in commands]
    assert modules[6:9] == [
        "llm_tuning_lab.train.accounting",
        "llm_tuning_lab.eval.predict",
        "llm_tuning_lab.eval.run_eval",
    ]
    assert modules[-2:] == ["llm_tuning_lab.eval.predict", "llm_tuning_lab.eval.run_eval"]
    assert "--copy-expected" in commands[7]
    assert "--copy-expected" in commands[-2]
    for eval_command in (commands[8], commands[-1]):
        assert "--strict" in eval_command
        assert eval_command[eval_command.index("--min-coverage") + 1] == "1.0"
        assert eval_command[eval_command.index("--min-fact-recall") + 1] == "0.8"
        assert eval_command[eval_command.index("--min-answer-similarity") + 1] == "0.75"
        assert eval_command[eval_command.index("--min-timeline-event-recall") + 1] == "0.6"


def test_load_pipeline_config_reads_required_paths() -> None:
    config = load_pipeline_config(Path("configs/run/react_react_qwen3_14b.yaml"))

    assert config.model_config == Path("configs/model/base.yaml")
    assert config.train_file == Path("data/processed/train.jsonl")
    assert config.bundle_file == Path("data/interim/bundles/react-react.jsonl")
    assert config.max_seq_length == 2048
    assert config.split_strategy == "thread_hash"
    assert config.strict_eval is False
    assert config.min_coverage is None


def test_load_h100_pipeline_config_adds_serious_accounting_fields() -> None:
    config = load_pipeline_config(Path("configs/run/react_react_h100_overnight.yaml"))

    assert config.gpu_vram_gb == 80
    assert config.model_tier == "h100_80gb"
    assert config.tokenizer_mode == "model"
    assert config.min_approved_gold_cases == 1000
    assert config.min_train_target_tokens == 1_000_000
    assert config.min_coverage == 1.0
    assert config.min_fact_recall == 0.7
    assert config.min_answer_similarity == 0.55
    assert config.min_timeline_event_recall == 0.6
    assert config.max_steps == 2000
    assert config.packing is True
    assert config.raft_output_dir == Path("outputs/sft/react-react-h100-overnight-raft")
    assert config.dpo_output_dir == Path("outputs/dpo/react-react-h100-overnight")

    commands = build_commands(config, skip_collect=True, insecure_ssl=False)
    accounting = next(command for command in commands if command[5] == "llm_tuning_lab.train.accounting")
    assert "--serious" in accounting
    assert accounting[accounting.index("--min-records") + 1] == "1000"
    assert accounting[accounting.index("--min-target-tokens") + 1] == "1000000"
    assert accounting[accounting.index("--gpu-vram-gb") + 1] == "80.0"
    assert accounting[accounting.index("--model-tier") + 1] == "h100_80gb"
    modules = [command[5] for command in commands]
    assert modules.count("llm_tuning_lab.train.sft") == 4
    assert "llm_tuning_lab.train.dpo" in modules
    assert modules[-2:] == ["llm_tuning_lab.eval.predict", "llm_tuning_lab.eval.run_eval"]
    for command in commands:
        if command[5] == "llm_tuning_lab.eval.run_eval":
            assert "--strict" in command
            assert command[command.index("--min-coverage") + 1] == "1.0"
            assert command[command.index("--min-fact-recall") + 1] == "0.7"
    dpo_command = next(command for command in commands if command[5] == "llm_tuning_lab.train.dpo")
    assert "--sft-adapter-path" in dpo_command
    assert dpo_command[dpo_command.index("--sft-adapter-path") + 1] == (
        "outputs/sft/react-react-h100-overnight-raft"
    )


def test_resolve_preset_uses_alias() -> None:
    assert resolve_preset("react-react-qwen3-14b") == Path("configs/run/react_react_qwen3_14b.yaml")


def test_resolve_preset_rejects_unknown_name() -> None:
    with pytest.raises(FileNotFoundError):
        resolve_preset("missing-preset")


def _pipeline_config(**overrides: object) -> PipelineConfig:
    values = {
        "collect_config": Path("configs/collect/react_react.yaml"),
        "raw_dir": Path("data/raw/github/react-react"),
        "data_config": Path("configs/data/react_react_sft.yaml"),
        "model_config": Path("configs/model/base.yaml"),
        "train_config": Path("configs/train/sft.yaml"),
        "lora_config": Path("configs/train/lora.yaml"),
        "train_file": Path("data/processed/train.jsonl"),
        "validation_file": Path("data/processed/validation.jsonl"),
        "test_file": Path("data/processed/test.jsonl"),
        "bundle_file": Path("data/interim/bundles/react-react.jsonl"),
        "gold_cases_file": Path("data/interim/gold_cases/react-react.jsonl"),
        "benchmark_file": Path("evals/benchmarks/react-react.jsonl"),
        "baseline_predictions": Path("evals/results/base_rag_predictions.jsonl"),
        "post_train_predictions": Path("evals/results/sft_rag_predictions.jsonl"),
        "baseline_metrics": Path("evals/results/base_rag_metrics.json"),
        "post_train_metrics": Path("evals/results/sft_rag_metrics.json"),
        "output_dir": Path("outputs/sft/react-react-qwen3-14b"),
        "copy_expected_predictions": False,
        "strict_eval": False,
        "min_coverage": None,
        "min_fact_recall": None,
        "min_answer_similarity": None,
        "min_timeline_event_recall": None,
        "gpu_vram_gb": None,
        "gpu_mode": None,
        "model_tier": None,
        "min_approved_gold_cases": None,
        "min_train_target_tokens": None,
        "tokenizer_mode": "whitespace",
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 1,
        "max_steps": None,
        "num_train_epochs": 1,
        "packing": False,
        "raft_data_config": None,
        "raft_train_file": None,
        "raft_validation_file": None,
        "raft_output_dir": None,
        "raft_predictions": None,
        "raft_metrics": None,
        "dpo_data_config": None,
        "dpo_train_config": None,
        "dpo_train_file": None,
        "dpo_validation_file": None,
        "dpo_output_dir": None,
        "dpo_predictions": None,
        "dpo_metrics": None,
        "max_pages": 1,
        "per_page": 10,
        "validation_ratio": 0.1,
        "test_ratio": 0.1,
        "max_seq_length": 2048,
        "split_strategy": "thread_hash",
        "validation_repositories": (),
        "test_repositories": (),
        "min_evidence_per_bundle": 3,
        "require_approved_gold_cases": True,
    }
    values.update(overrides)
    return PipelineConfig(**values)
