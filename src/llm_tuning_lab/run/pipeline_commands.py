from __future__ import annotations

from pathlib import Path
from typing import Any


def run_eval_command(config: Any, *, predictions: Path, output: Path) -> list[str]:
    command = [
        "uv",
        "run",
        "--system-certs",
        "python",
        "-m",
        "llm_tuning_lab.eval.run_eval",
        "--benchmark",
        _command_path(config.benchmark_file),
        "--predictions",
        _command_path(predictions),
        "--output",
        _command_path(output),
    ]
    if config.strict_eval:
        command.append("--strict")
    _append_threshold(command, "--min-coverage", config.min_coverage)
    _append_threshold(command, "--min-fact-recall", config.min_fact_recall)
    _append_threshold(command, "--min-answer-similarity", config.min_answer_similarity)
    _append_threshold(command, "--min-timeline-event-recall", config.min_timeline_event_recall)
    return command


def append_predict_flags(commands: list[list[str]], config: Any) -> None:
    if not config.copy_expected_predictions:
        return
    for command in commands:
        if "llm_tuning_lab.eval.predict" in command:
            command.append("--copy-expected")


def optional_raft_and_dpo_commands(config: Any) -> list[list[str]]:
    if not all(
        (
            config.raft_data_config,
            config.raft_train_file,
            config.raft_validation_file,
            config.raft_output_dir,
            config.raft_predictions,
            config.raft_metrics,
            config.dpo_data_config,
            config.dpo_train_config,
            config.dpo_train_file,
            config.dpo_validation_file,
            config.dpo_output_dir,
            config.dpo_predictions,
            config.dpo_metrics,
        )
    ):
        return []

    return [
        _roadmap_command(
            "raft",
            config,
            train_file=config.raft_train_file,
            validation_file=config.raft_validation_file,
            extra=["--max-seq-length", str(config.max_seq_length)],
        ),
        _validate_command(config.raft_train_file),
        _validate_command(config.raft_validation_file),
        sft_command(
            config,
            data_config=config.raft_data_config,
            train_file=config.raft_train_file,
            validation_file=config.raft_validation_file,
            output_dir=config.raft_output_dir,
            adapter_input=config.output_dir,
            preflight=True,
        ),
        sft_command(
            config,
            data_config=config.raft_data_config,
            train_file=config.raft_train_file,
            validation_file=config.raft_validation_file,
            output_dir=config.raft_output_dir,
            adapter_input=config.output_dir,
            preflight=False,
        ),
        predict_command(config, adapter_path=config.raft_output_dir, output=config.raft_predictions),
        run_eval_command(config, predictions=config.raft_predictions, output=config.raft_metrics),
        _roadmap_command(
            "dpo",
            config,
            train_file=config.dpo_train_file,
            validation_file=config.dpo_validation_file,
            extra=[],
        ),
        _validate_command(config.dpo_train_file, data_format="dpo"),
        _validate_command(config.dpo_validation_file, data_format="dpo"),
        dpo_command(config, preflight=True),
        dpo_command(config, preflight=False),
        predict_command(config, adapter_path=config.dpo_output_dir, output=config.dpo_predictions),
        run_eval_command(config, predictions=config.dpo_predictions, output=config.dpo_metrics),
    ]


def accounting_command(config: Any) -> list[str]:
    command = [
        "uv",
        "run",
        "--system-certs",
        "python",
        "-m",
        "llm_tuning_lab.train.accounting",
        "--train-file",
        _command_path(config.train_file),
        "--validation-file",
        _command_path(config.validation_file),
        "--model-config",
        _command_path(config.model_config),
        "--tokenizer-mode",
        config.tokenizer_mode,
        "--max-seq-length",
        str(config.max_seq_length),
        "--per-device-train-batch-size",
        str(config.per_device_train_batch_size),
        "--gradient-accumulation-steps",
        str(config.gradient_accumulation_steps),
        "--num-train-epochs",
        str(config.num_train_epochs),
    ]
    if config.max_steps is not None:
        command.extend(["--max-steps", str(config.max_steps)])
    if config.packing:
        command.append("--packing")
    if config.min_approved_gold_cases is not None or config.min_train_target_tokens is not None:
        command.append("--serious")
        command.extend(["--min-records", str(config.min_approved_gold_cases or 1000)])
        command.extend(["--min-target-tokens", str(config.min_train_target_tokens or 1_000_000)])
    if config.gpu_vram_gb is not None:
        command.extend(["--gpu-vram-gb", str(config.gpu_vram_gb)])
    if config.model_tier:
        command.extend(["--model-tier", config.model_tier])
    return command


def predict_command(config: Any, *, adapter_path: Path | None, output: Path) -> list[str]:
    command = [
        "uv",
        "run",
        "--system-certs",
        "python",
        "-m",
        "llm_tuning_lab.eval.predict",
        "--model-config",
        _command_path(config.model_config),
    ]
    if adapter_path is not None:
        command.extend(["--adapter-path", _command_path(adapter_path)])
    command.extend(
        [
            "--benchmark",
            _command_path(config.benchmark_file),
            "--output",
            _command_path(output),
        ]
    )
    return command


def sft_command(
    config: Any,
    *,
    data_config: Path,
    train_file: Path,
    validation_file: Path,
    output_dir: Path,
    adapter_input: Path | None,
    preflight: bool,
) -> list[str]:
    command = [
        "uv",
        "run",
        "--system-certs",
        "python",
        "-m",
        "llm_tuning_lab.train.sft",
        "--model-config",
        _command_path(config.model_config),
        "--data-config",
        _command_path(data_config),
        "--train-config",
        _command_path(config.train_config),
        "--lora-config",
        _command_path(config.lora_config),
        "--train-file",
        _command_path(train_file),
        "--validation-file",
        _command_path(validation_file),
        "--output-dir",
        _command_path(output_dir),
    ]
    if adapter_input is not None:
        command.extend(["--adapter-input", _command_path(adapter_input)])
    if preflight:
        command.append("--preflight-only")
    return command


def dpo_command(config: Any, *, preflight: bool) -> list[str]:
    command = [
        "uv",
        "run",
        "--system-certs",
        "python",
        "-m",
        "llm_tuning_lab.train.dpo",
        "--model-config",
        _command_path(config.model_config),
        "--data-config",
        _command_path(config.dpo_data_config),
        "--train-config",
        _command_path(config.dpo_train_config),
        "--lora-config",
        _command_path(config.lora_config),
        "--train-file",
        _command_path(config.dpo_train_file),
        "--validation-file",
        _command_path(config.dpo_validation_file),
        "--output-dir",
        _command_path(config.dpo_output_dir),
        "--sft-adapter-path",
        _command_path(config.raft_output_dir),
    ]
    if preflight:
        command.append("--preflight-only")
    return command


def _roadmap_command(
    mode: str,
    config: Any,
    *,
    train_file: Path,
    validation_file: Path,
    extra: list[str],
) -> list[str]:
    return [
        "uv",
        "run",
        "--system-certs",
        "python",
        "-m",
        "llm_tuning_lab.data.roadmap",
        mode,
        "--bundles",
        _command_path(config.bundle_file),
        "--gold-cases",
        _command_path(config.gold_cases_file),
        "--train-output",
        _command_path(train_file),
        "--validation-output",
        _command_path(validation_file),
        *extra,
    ]


def _validate_command(path: Path, *, data_format: str | None = None) -> list[str]:
    command = [
        "uv",
        "run",
        "--system-certs",
        "python",
        "-m",
        "llm_tuning_lab.data.validate",
        _command_path(path),
    ]
    if data_format:
        command.extend(["--format", data_format])
    return command


def _append_threshold(command: list[str], flag: str, value: float | None) -> None:
    if value is not None:
        command.extend([flag, str(value)])


def _command_path(path: Path) -> str:
    return str(path).replace("\\", "/")
