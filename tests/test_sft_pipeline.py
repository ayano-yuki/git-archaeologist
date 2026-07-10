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
        output_dir=Path("outputs/sft/react-react-qwen3-14b"),
        max_pages=1,
        per_page=10,
        validation_ratio=0.2,
    )

    commands = build_commands(config, skip_collect=True, insecure_ssl=False)

    assert all("llm_tuning_lab.collect.github" not in command for command in commands)
    assert commands[0][5] == "llm_tuning_lab.data.prepare"
    assert commands[-2][5] == "llm_tuning_lab.train.sft"
    assert "--preflight-only" in commands[-2]
    assert commands[-1][5] == "llm_tuning_lab.train.sft"
    assert "--output-dir" in commands[-1]


def test_load_pipeline_config_reads_required_paths() -> None:
    config = load_pipeline_config(Path("configs/run/react_react_qwen3_14b.yaml"))

    assert config.model_config == Path("configs/model/base.yaml")
    assert config.train_file == Path("data/processed/train.jsonl")


def test_resolve_preset_uses_alias() -> None:
    assert resolve_preset("react-react-qwen3-14b") == Path("configs/run/react_react_qwen3_14b.yaml")


def test_resolve_preset_rejects_unknown_name() -> None:
    with pytest.raises(FileNotFoundError):
        resolve_preset("missing-preset")
