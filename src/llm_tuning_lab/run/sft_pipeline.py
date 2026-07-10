from __future__ import annotations

import argparse
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm_tuning_lab.config import load_yaml


@dataclass(frozen=True)
class PipelineConfig:
    collect_config: Path
    raw_dir: Path
    data_config: Path
    model_config: Path
    train_config: Path
    lora_config: Path
    train_file: Path
    validation_file: Path
    test_file: Path
    bundle_file: Path
    gold_cases_file: Path
    benchmark_file: Path
    baseline_predictions: Path
    post_train_predictions: Path
    baseline_metrics: Path
    post_train_metrics: Path
    output_dir: Path
    max_pages: int | None
    per_page: int | None
    validation_ratio: float
    test_ratio: float
    min_evidence_per_bundle: int
    require_approved_gold_cases: bool


def build_commands(
    config: PipelineConfig,
    *,
    skip_collect: bool,
    insecure_ssl: bool,
) -> list[list[str]]:
    commands: list[list[str]] = []
    if not skip_collect:
        collect_command = [
            "uv",
            "run",
            "--system-certs",
            "python",
            "-m",
            "llm_tuning_lab.collect.github",
            "--config",
            _command_path(config.collect_config),
        ]
        if config.max_pages is not None:
            collect_command.extend(["--max-pages", str(config.max_pages)])
        if config.per_page is not None:
            collect_command.extend(["--per-page", str(config.per_page)])
        if insecure_ssl:
            collect_command.append("--insecure-ssl")
        commands.append(collect_command)

    commands.extend(
        [
            [
                "uv",
                "run",
                "--system-certs",
                "python",
                "-m",
                "llm_tuning_lab.data.bundles",
                "--input",
                _command_path(config.raw_dir),
                "--output",
                _command_path(config.bundle_file),
                "--min-evidence-per-bundle",
                str(config.min_evidence_per_bundle),
            ],
            [
                "uv",
                "run",
                "--system-certs",
                "python",
                "-m",
                "llm_tuning_lab.data.gold_cases",
                "validate",
                "--bundles",
                _command_path(config.bundle_file),
                "--gold-cases",
                _command_path(config.gold_cases_file),
            ],
            [
                "uv",
                "run",
                "--system-certs",
                "python",
                "-m",
                "llm_tuning_lab.data.gold_cases",
                "materialize",
                "--bundles",
                _command_path(config.bundle_file),
                "--gold-cases",
                _command_path(config.gold_cases_file),
                "--train-output",
                _command_path(config.train_file),
                "--validation-output",
                _command_path(config.validation_file),
                "--test-output",
                _command_path(config.test_file),
                "--benchmark-output",
                _command_path(config.benchmark_file),
                "--validation-ratio",
                str(config.validation_ratio),
                "--test-ratio",
                str(config.test_ratio),
            ],
            [
                "uv",
                "run",
                "--system-certs",
                "python",
                "-m",
                "llm_tuning_lab.data.validate",
                _command_path(config.train_file),
            ],
            [
                "uv",
                "run",
                "--system-certs",
                "python",
                "-m",
                "llm_tuning_lab.data.validate",
                _command_path(config.validation_file),
            ],
            [
                "uv",
                "run",
                "--system-certs",
                "python",
                "-m",
                "llm_tuning_lab.data.validate",
                _command_path(config.test_file),
            ],
            [
                "uv",
                "run",
                "--system-certs",
                "python",
                "-m",
                "llm_tuning_lab.eval.run_eval",
                "--benchmark",
                _command_path(config.benchmark_file),
                "--predictions",
                _command_path(config.baseline_predictions),
                "--output",
                _command_path(config.baseline_metrics),
            ],
            [
                "uv",
                "run",
                "--system-certs",
                "python",
                "-m",
                "llm_tuning_lab.train.sft",
                "--model-config",
                _command_path(config.model_config),
                "--data-config",
                _command_path(config.data_config),
                "--train-config",
                _command_path(config.train_config),
                "--lora-config",
                _command_path(config.lora_config),
                "--train-file",
                _command_path(config.train_file),
                "--validation-file",
                _command_path(config.validation_file),
                "--output-dir",
                _command_path(config.output_dir),
                "--preflight-only",
            ],
            [
                "uv",
                "run",
                "--system-certs",
                "python",
                "-m",
                "llm_tuning_lab.train.sft",
                "--model-config",
                _command_path(config.model_config),
                "--data-config",
                _command_path(config.data_config),
                "--train-config",
                _command_path(config.train_config),
                "--lora-config",
                _command_path(config.lora_config),
                "--train-file",
                _command_path(config.train_file),
                "--validation-file",
                _command_path(config.validation_file),
                "--output-dir",
                _command_path(config.output_dir),
            ],
            [
                "uv",
                "run",
                "--system-certs",
                "python",
                "-m",
                "llm_tuning_lab.eval.run_eval",
                "--benchmark",
                _command_path(config.benchmark_file),
                "--predictions",
                _command_path(config.post_train_predictions),
                "--output",
                _command_path(config.post_train_metrics),
            ],
        ]
    )
    if not config.require_approved_gold_cases:
        materialize_command = commands[2 if skip_collect else 3]
        materialize_command.append("--allow-unapproved")
    return commands


def load_pipeline_config(path: Path) -> PipelineConfig:
    loaded = load_yaml(path)
    return PipelineConfig(
        collect_config=Path(_required(loaded, "collect_config")),
        raw_dir=Path(_required(loaded, "raw_dir")),
        data_config=Path(_required(loaded, "data_config")),
        model_config=Path(_required(loaded, "model_config")),
        train_config=Path(_required(loaded, "train_config")),
        lora_config=Path(_required(loaded, "lora_config")),
        train_file=Path(_required(loaded, "train_file")),
        validation_file=Path(_required(loaded, "validation_file")),
        test_file=Path(_required(loaded, "test_file")),
        bundle_file=Path(_required(loaded, "bundle_file")),
        gold_cases_file=Path(_required(loaded, "gold_cases_file")),
        benchmark_file=Path(_required(loaded, "benchmark_file")),
        baseline_predictions=Path(_required(loaded, "baseline_predictions")),
        post_train_predictions=Path(_required(loaded, "post_train_predictions")),
        baseline_metrics=Path(_required(loaded, "baseline_metrics")),
        post_train_metrics=Path(_required(loaded, "post_train_metrics")),
        output_dir=Path(_required(loaded, "output_dir")),
        max_pages=_optional_int(loaded.get("max_pages")),
        per_page=_optional_int(loaded.get("per_page")),
        validation_ratio=float(loaded.get("validation_ratio", 0.1)),
        test_ratio=float(loaded.get("test_ratio", 0.1)),
        min_evidence_per_bundle=int(loaded.get("min_evidence_per_bundle", 3)),
        require_approved_gold_cases=bool(loaded.get("require_approved_gold_cases", True)),
    )


def resolve_preset(value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate

    preset_name = value.replace("-", "_")
    preset_path = Path("configs/run") / f"{preset_name}.yaml"
    if preset_path.exists():
        return preset_path

    raise FileNotFoundError(
        f"Unknown preset '{value}'. Use a config path or add {preset_path}."
    )


def run_commands(commands: list[list[str]], *, dry_run: bool) -> None:
    for command in commands:
        print(shlex.join(command))
        if not dry_run:
            subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Linux SFT pipeline preset.")
    parser.add_argument("--preset", default="react-react-qwen3-14b")
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument("--insecure-ssl", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-sync-command", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_pipeline_config(resolve_preset(args.preset))

    commands = build_commands(
        config,
        skip_collect=args.skip_collect,
        insecure_ssl=args.insecure_ssl,
    )
    if args.include_sync_command:
        commands.insert(0, ["uv", "sync", "--system-certs", "--extra", "train", "--group", "dev"])

    if args.skip_collect and not args.dry_run:
        _ensure_raw_data_exists(config.raw_dir)

    run_commands(commands, dry_run=args.dry_run)
    return 0


def _required(config: dict[str, Any], key: str) -> Any:
    value = config.get(key)
    if value in (None, ""):
        raise ValueError(f"run preset must define '{key}'")
    return value


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _ensure_raw_data_exists(raw_dir: Path) -> None:
    if not raw_dir.exists():
        raise FileNotFoundError(
            f"--skip-collect was set, but raw data directory does not exist: {raw_dir}"
        )
    if not any(raw_dir.glob("*.jsonl")):
        raise FileNotFoundError(
            f"--skip-collect was set, but no JSONL files were found under: {raw_dir}"
        )


def _command_path(path: Path) -> str:
    return str(path).replace("\\", "/")


if __name__ == "__main__":
    raise SystemExit(main())
