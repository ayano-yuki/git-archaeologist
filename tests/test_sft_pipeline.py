from pathlib import Path

import pytest

from llm_tuning_lab.run.sft_pipeline import (
    PipelineConfig,
    build_commands,
    load_pipeline_config,
    resolve_preset,
)


def test_build_commands_can_skip_collect() -> None:
    config = PipelineConfig(
        collect_config=Path("configs/collect/react_react.yaml"),
        raw_dir=Path("data/raw/github/react-react"),
        data_config=Path("configs/data/react_react_sft.yaml"),
        model_config=Path("configs/model/base.yaml"),
        train_config=Path("configs/train/sft.yaml"),
        lora_config=Path("configs/train/lora.yaml"),
        train_file=Path("data/processed/train.jsonl"),
        validation_file=Path("data/processed/validation.jsonl"),
        test_file=Path("data/processed/test.jsonl"),
        bundle_file=Path("data/interim/bundles/react-react.jsonl"),
        gold_cases_file=Path("data/interim/gold_cases/react-react.jsonl"),
        benchmark_file=Path("evals/benchmarks/react-react.jsonl"),
        baseline_predictions=Path("evals/results/base_rag_predictions.jsonl"),
        post_train_predictions=Path("evals/results/sft_rag_predictions.jsonl"),
        baseline_metrics=Path("evals/results/base_rag_metrics.json"),
        post_train_metrics=Path("evals/results/sft_rag_metrics.json"),
        output_dir=Path("outputs/sft/react-react-qwen3-14b"),
        max_pages=1,
        per_page=10,
        validation_ratio=0.1,
        test_ratio=0.1,
        max_seq_length=2048,
        split_strategy="thread_hash",
        validation_repositories=(),
        test_repositories=(),
        min_evidence_per_bundle=3,
        require_approved_gold_cases=True,
    )

    commands = build_commands(config, skip_collect=True, insecure_ssl=False)

    assert all("llm_tuning_lab.collect.github" not in command for command in commands)
    assert commands[0][5] == "llm_tuning_lab.data.bundles"
    assert commands[1][5] == "llm_tuning_lab.data.gold_cases"
    assert commands[1][6] == "validate"
    assert commands[2][5] == "llm_tuning_lab.data.gold_cases"
    assert commands[2][6] == "materialize"
    assert "--max-seq-length" in commands[2]
    assert "--split-strategy" in commands[2]
    assert commands[6][5] == "llm_tuning_lab.eval.run_eval"
    assert commands[-3][5] == "llm_tuning_lab.train.sft"
    assert "--preflight-only" in commands[-3]
    assert commands[-2][5] == "llm_tuning_lab.train.sft"
    assert commands[-1][5] == "llm_tuning_lab.eval.run_eval"


def test_load_pipeline_config_reads_required_paths() -> None:
    config = load_pipeline_config(Path("configs/run/react_react_qwen3_14b.yaml"))

    assert config.model_config == Path("configs/model/base.yaml")
    assert config.train_file == Path("data/processed/train.jsonl")
    assert config.bundle_file == Path("data/interim/bundles/react-react.jsonl")
    assert config.max_seq_length == 2048
    assert config.split_strategy == "thread_hash"


def test_resolve_preset_uses_alias() -> None:
    assert resolve_preset("react-react-qwen3-14b") == Path("configs/run/react_react_qwen3_14b.yaml")


def test_resolve_preset_rejects_unknown_name() -> None:
    with pytest.raises(FileNotFoundError):
        resolve_preset("missing-preset")
