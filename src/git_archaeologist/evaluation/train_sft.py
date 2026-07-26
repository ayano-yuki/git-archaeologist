"""QLoRA training entry point for the answer-discipline SFT dataset."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import importlib.util
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from git_archaeologist.evaluation.runtime_profile import (
    ModelRole,
    build_runtime_profile,
)
from git_archaeologist.evaluation.sft_data_policy import SFTRecord
from git_archaeologist.evaluation.sft_dataset import load_sft_jsonl, validate_sft_dataset
from git_archaeologist.evaluation.sft_training_plan import (
    SFTTrainingPlan,
    load_sft_training_plan,
)


DEFAULT_PLAN_PATH = Path("data/baseline-rag/sft/answer-discipline/lora-training-plan.json")
REQUIRED_TRAINING_MODULES = (
    "accelerate",
    "bitsandbytes",
    "datasets",
    "peft",
    "torch",
    "transformers",
)


@dataclass(frozen=True)
class SFTDryRunReport:
    """Dry-run summary that does not import heavyweight training runtimes."""

    status: str
    plan_path: str
    should_train: bool
    method: str
    base_model: str
    dataset_path: str
    record_count: int
    split_counts: dict[str, int]
    output_dir: str
    runtime_answer_judge_status: str
    runtime_answer_judge_reason: str
    missing_optional_dependencies: tuple[str, ...]
    execute_ready: bool
    command_hint: str


def build_training_text(record: SFTRecord) -> str:
    """Render one reviewed SFT record as a causal-LM training sample."""

    evidence_lines = []
    for item in record.evidence_pack["evidence_items"]:
        evidence_lines.append(
            "\n".join(
                (
                    f"- source_id: {item['source_id']}",
                    f"  kind: {item['artifact_kind']}",
                    f"  url: {item['source_url']}",
                    f"  excerpt: {item['excerpt']}",
                )
            )
        )

    ideal_answer = record.ideal_answer
    target = record.target
    labels = record.labels
    return "\n".join(
        (
            "### System",
            (
                "Answer only from the Evidence Pack. Separate supported facts, "
                "inference, and unknowns. Cite source IDs for every supported claim."
            ),
            "### Repository",
            record.source_repository,
            "### Task",
            str(labels.get("task", "answer_discipline")),
            "### Target",
            json.dumps(dict(target), ensure_ascii=False, sort_keys=True),
            "### Question",
            record.question,
            "### Evidence Pack",
            "\n".join(evidence_lines),
            "### Ideal Answer",
            json.dumps(dict(ideal_answer), ensure_ascii=False, sort_keys=True),
            "",
        )
    )


def build_dry_run_report(
    plan_path: Path = DEFAULT_PLAN_PATH,
    *,
    dependency_names: Sequence[str] = REQUIRED_TRAINING_MODULES,
) -> SFTDryRunReport:
    """Validate the FT plan, dataset, runtime profile, and optional deps."""

    plan = load_sft_training_plan(plan_path)
    dataset_path = _resolve_path(plan.dataset_path)
    output_dir = _resolve_path(plan.output_dir)
    dataset_report = validate_sft_dataset(dataset_path)
    profile = build_runtime_profile(disk_path=Path.cwd())
    answer_judge_check = _find_answer_judge_check(profile.constraint_checks)
    missing_dependencies = _missing_optional_dependencies(dependency_names)
    execute_ready = (
        plan.should_train
        and answer_judge_check.status == "ready"
        and not missing_dependencies
    )
    return SFTDryRunReport(
        status="sft_dry_run_passed",
        plan_path=str(plan_path),
        should_train=plan.should_train,
        method=plan.method,
        base_model=plan.base_model,
        dataset_path=str(dataset_path),
        record_count=dataset_report.record_count,
        split_counts=dataset_report.split_counts,
        output_dir=str(output_dir),
        runtime_answer_judge_status=answer_judge_check.status,
        runtime_answer_judge_reason=answer_judge_check.reason,
        missing_optional_dependencies=missing_dependencies,
        execute_ready=execute_ready,
        command_hint=(
            "uv run --extra training python -m git_archaeologist.evaluation.train_sft "
            f"--plan {_display_path(plan_path)} --execute"
        ),
    )


def run_qlora_training(
    plan_path: Path = DEFAULT_PLAN_PATH,
    *,
    max_steps: int | None = None,
    dataset_limit: int | None = None,
) -> dict[str, object]:
    """Run QLoRA adapter training and return a serializable summary."""

    plan = load_sft_training_plan(plan_path)
    dry_run = build_dry_run_report(plan_path)
    if not plan.should_train:
        raise RuntimeError(f"SFT plan is not ready to train: {plan.reason}")
    if dry_run.runtime_answer_judge_status != "ready":
        raise RuntimeError(
            "Answer/Judge runtime is not ready: "
            f"{dry_run.runtime_answer_judge_status} - {dry_run.runtime_answer_judge_reason}"
        )
    if dry_run.missing_optional_dependencies:
        missing = ", ".join(dry_run.missing_optional_dependencies)
        raise RuntimeError(
            "missing training optional dependencies: "
            f"{missing}. Install them with: uv sync --extra training"
        )

    return _run_qlora_training_with_optional_dependencies(
        plan,
        max_steps=max_steps,
        dataset_limit=dataset_limit,
    )


def dry_run_report_to_dict(report: SFTDryRunReport) -> dict[str, object]:
    """Return a JSON-friendly dry-run report."""

    payload = asdict(report)
    payload["missing_optional_dependencies"] = list(report.missing_optional_dependencies)
    return payload


def _run_qlora_training_with_optional_dependencies(
    plan: SFTTrainingPlan,
    *,
    max_steps: int | None,
    dataset_limit: int | None,
) -> dict[str, object]:
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    records = tuple(
        record
        for record in load_sft_jsonl(_resolve_path(plan.dataset_path))
        if record.split.value == "train"
    )
    if dataset_limit is not None:
        records = records[:dataset_limit]
    if not records:
        raise RuntimeError("training split must contain at least one SFT record")

    training_args = dict(plan.training_args)
    max_seq_length = int(training_args.get("max_seq_length", 4096))
    output_dir = _resolve_path(plan.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(plan.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    compute_dtype = (
        torch.bfloat16
        if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
        else torch.float16
    )
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        plan.base_model,
        quantization_config=quantization_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)
    lora_config = LoraConfig(
        r=int(training_args.get("lora_r", 16)),
        lora_alpha=int(training_args.get("lora_alpha", 32)),
        lora_dropout=float(training_args.get("lora_dropout", 0.05)),
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=tuple(
            training_args.get(
                "target_modules",
                (
                    "q_proj",
                    "k_proj",
                    "v_proj",
                    "o_proj",
                    "gate_proj",
                    "up_proj",
                    "down_proj",
                ),
            )
        ),
    )
    model = get_peft_model(model, lora_config)

    dataset = Dataset.from_dict({"text": [build_training_text(record) for record in records]})

    def tokenize_batch(batch: dict[str, list[str]]) -> dict[str, list[list[int]]]:
        tokenized = tokenizer(
            batch["text"],
            truncation=True,
            max_length=max_seq_length,
            padding=False,
        )
        tokenized["labels"] = [input_ids.copy() for input_ids in tokenized["input_ids"]]
        return tokenized

    tokenized_dataset = dataset.map(tokenize_batch, batched=True, remove_columns=["text"])
    trainer_args = TrainingArguments(
        output_dir=str(output_dir),
        max_steps=max_steps if max_steps is not None else -1,
        num_train_epochs=float(training_args.get("num_train_epochs", 1)),
        per_device_train_batch_size=int(training_args.get("per_device_train_batch_size", 1)),
        gradient_accumulation_steps=int(training_args.get("gradient_accumulation_steps", 8)),
        learning_rate=float(training_args.get("learning_rate", 2e-4)),
        logging_steps=int(training_args.get("logging_steps", 1)),
        save_strategy="no",
        report_to=[],
        remove_unused_columns=False,
        seed=plan.seed,
        bf16=compute_dtype is torch.bfloat16,
        fp16=compute_dtype is torch.float16,
        optim=str(training_args.get("optim", "paged_adamw_8bit")),
    )
    trainer = Trainer(
        model=model,
        args=trainer_args,
        train_dataset=tokenized_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )
    train_result = trainer.train()
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    summary = {
        "status": "sft_training_completed",
        "method": plan.method,
        "base_model": plan.base_model,
        "dataset_path": plan.dataset_path,
        "record_count": len(records),
        "output_dir": str(output_dir),
        "max_steps": max_steps,
        "metrics": dict(train_result.metrics),
    }
    (output_dir / "training-run-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _find_answer_judge_check(checks: Iterable[Any]) -> Any:
    for check in checks:
        if check.role is ModelRole.ANSWER_JUDGE:
            return check
    raise RuntimeError("runtime profile did not include an answer_judge constraint check")


def _missing_optional_dependencies(dependency_names: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        dependency_name
        for dependency_name in dependency_names
        if importlib.util.find_spec(dependency_name) is None
    )


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _display_path(path: Path) -> str:
    return path.as_posix()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="validate inputs without training")
    mode.add_argument("--execute", action="store_true", help="run QLoRA adapter training")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--dataset-limit", type=int, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.execute:
        payload = run_qlora_training(
            args.plan,
            max_steps=args.max_steps,
            dataset_limit=args.dataset_limit,
        )
    else:
        payload = dry_run_report_to_dict(build_dry_run_report(args.plan))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
