from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from llm_tuning_lab.config import load_yaml


class TokenizerLike(Protocol):
    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]: ...


@dataclass(frozen=True)
class AccountingStats:
    record_count: int
    total_tokens: int
    target_tokens: int
    p50_length: int
    p95_length: int
    max_length: int
    over_max_length_count: int
    effective_batch_size: int
    estimated_optimizer_steps: int
    tokens_per_step: int
    expected_total_trained_tokens: int

    def as_dict(self) -> dict[str, int]:
        return {
            "record_count": self.record_count,
            "total_tokens": self.total_tokens,
            "target_tokens": self.target_tokens,
            "p50_length": self.p50_length,
            "p95_length": self.p95_length,
            "max_length": self.max_length,
            "over_max_length_count": self.over_max_length_count,
            "effective_batch_size": self.effective_batch_size,
            "estimated_optimizer_steps": self.estimated_optimizer_steps,
            "tokens_per_step": self.tokens_per_step,
            "expected_total_trained_tokens": self.expected_total_trained_tokens,
        }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            loaded = json.loads(stripped)
            if not isinstance(loaded, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object.")
            records.append(loaded)
    return records


def compute_jsonl_accounting(
    path: Path,
    *,
    tokenizer: TokenizerLike | None = None,
    max_seq_length: int,
    per_device_train_batch_size: int = 1,
    gradient_accumulation_steps: int = 1,
    max_steps: int | None = None,
    num_train_epochs: int = 1,
    packing: bool = False,
) -> AccountingStats:
    return compute_accounting(
        read_jsonl(path),
        tokenizer=tokenizer,
        max_seq_length=max_seq_length,
        per_device_train_batch_size=per_device_train_batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        max_steps=max_steps,
        num_train_epochs=num_train_epochs,
        packing=packing,
    )


def compute_accounting(
    records: Iterable[Mapping[str, Any]],
    *,
    tokenizer: TokenizerLike | None = None,
    max_seq_length: int,
    per_device_train_batch_size: int = 1,
    gradient_accumulation_steps: int = 1,
    max_steps: int | None = None,
    num_train_epochs: int = 1,
    packing: bool = False,
) -> AccountingStats:
    lengths: list[int] = []
    total_tokens = 0
    target_tokens = 0

    for record in records:
        record_total, record_target, record_length = _record_token_counts(record, tokenizer)
        total_tokens += record_total
        target_tokens += record_target
        lengths.append(record_length)

    record_count = len(lengths)
    effective_batch_size = per_device_train_batch_size * gradient_accumulation_steps
    if effective_batch_size < 1:
        raise ValueError("effective batch size must be at least 1.")
    if max_seq_length < 1:
        raise ValueError("max_seq_length must be at least 1.")
    if num_train_epochs < 1:
        raise ValueError("num_train_epochs must be at least 1.")

    steps_per_epoch = math.ceil(record_count / effective_batch_size) if record_count else 0
    estimated_steps = max_steps if max_steps is not None else steps_per_epoch * num_train_epochs
    if estimated_steps < 0:
        raise ValueError("max_steps must be non-negative.")

    if packing:
        tokens_per_step = effective_batch_size * max_seq_length
    elif steps_per_epoch:
        tokens_per_step = math.ceil(total_tokens / steps_per_epoch)
    else:
        tokens_per_step = 0

    return AccountingStats(
        record_count=record_count,
        total_tokens=total_tokens,
        target_tokens=target_tokens,
        p50_length=_percentile(lengths, 50),
        p95_length=_percentile(lengths, 95),
        max_length=max(lengths, default=0),
        over_max_length_count=sum(length > max_seq_length for length in lengths),
        effective_batch_size=effective_batch_size,
        estimated_optimizer_steps=estimated_steps,
        tokens_per_step=tokens_per_step,
        expected_total_trained_tokens=tokens_per_step * estimated_steps,
    )


def validate_serious_gates(
    stats: AccountingStats,
    *,
    validation_record_count: int,
    min_records: int,
    min_target_tokens: int,
    max_seq_length: int,
    gpu_vram_gb: int | float | None,
    model_tier: str | None,
) -> list[str]:
    errors: list[str] = []
    if stats.record_count < min_records:
        errors.append(f"record_count {stats.record_count} is below required minimum {min_records}.")
    if stats.target_tokens < min_target_tokens:
        errors.append(
            f"target_tokens {stats.target_tokens} is below required minimum {min_target_tokens}."
        )
    if validation_record_count < 1:
        errors.append("validation set must contain at least one record.")
    if stats.p95_length > max_seq_length:
        errors.append(f"p95_length {stats.p95_length} exceeds max_seq_length {max_seq_length}.")
    if model_tier == "top" and (gpu_vram_gb is None or gpu_vram_gb < 160):
        errors.append("top model tier requires gpu_vram_gb >= 160.")
    return errors


def assert_serious_gates(**kwargs: Any) -> None:
    errors = validate_serious_gates(**kwargs)
    if errors:
        raise ValueError("; ".join(errors))


def load_tokenizer_from_model_config(
    model_config_path: Path,
    *,
    tokenizer_mode: str,
) -> TokenizerLike | None:
    if tokenizer_mode == "whitespace":
        return None
    if tokenizer_mode != "model":
        raise ValueError("tokenizer_mode must be 'model' or 'whitespace'.")
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "transformers is required for tokenizer_mode=model. Install with: "
            "uv sync --system-certs --extra train --group dev"
        ) from exc
    model_config = load_yaml(model_config_path)
    return AutoTokenizer.from_pretrained(
        model_config["model_name_or_path"],
        trust_remote_code=model_config.get("trust_remote_code", False),
    )


def _record_token_counts(
    record: Mapping[str, Any], tokenizer: TokenizerLike | None
) -> tuple[int, int, int]:
    if isinstance(record.get("messages"), list):
        return _messages_token_counts(record, tokenizer)
    if all(isinstance(record.get(field), str) for field in ("prompt", "chosen", "rejected")):
        return _preference_token_counts(record, tokenizer)
    raise ValueError("record must use messages or prompt/chosen/rejected format.")


def _messages_token_counts(
    record: Mapping[str, Any], tokenizer: TokenizerLike | None
) -> tuple[int, int, int]:
    messages = record["messages"]
    if not isinstance(messages, list):
        raise ValueError("messages must be a list.")

    rendered_parts: list[str] = []
    target_tokens = 0
    for message in messages:
        if not isinstance(message, Mapping):
            raise ValueError("messages entries must be objects.")
        role = str(message.get("role", ""))
        content = str(message.get("content", ""))
        rendered_parts.append(f"{role}: {content}")
        if role == "assistant":
            target_tokens += _count_tokens(content, tokenizer)

    total_tokens = _count_tokens("\n".join(rendered_parts), tokenizer)
    return total_tokens, target_tokens, total_tokens


def _preference_token_counts(
    record: Mapping[str, Any], tokenizer: TokenizerLike | None
) -> tuple[int, int, int]:
    prompt = str(record["prompt"])
    chosen = str(record["chosen"])
    rejected = str(record["rejected"])

    prompt_tokens = _count_tokens(prompt, tokenizer)
    chosen_tokens = _count_tokens(chosen, tokenizer)
    rejected_tokens = _count_tokens(rejected, tokenizer)
    total_tokens = prompt_tokens + chosen_tokens + rejected_tokens
    sequence_length = max(prompt_tokens + chosen_tokens, prompt_tokens + rejected_tokens)
    return total_tokens, chosen_tokens + rejected_tokens, sequence_length


def _count_tokens(text: str, tokenizer: TokenizerLike | None) -> int:
    if tokenizer is None:
        return len(text.split())
    if hasattr(tokenizer, "encode"):
        return len(tokenizer.encode(text, add_special_tokens=False))

    encoded = tokenizer(text, add_special_tokens=False)  # type: ignore[operator]
    if isinstance(encoded, Mapping):
        input_ids = encoded.get("input_ids", [])
    else:
        input_ids = getattr(encoded, "input_ids", [])
    return len(input_ids)


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = math.ceil((percentile / 100) * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute and gate fine-tuning token accounting.")
    parser.add_argument("--train-file", type=Path, required=True)
    parser.add_argument("--validation-file", type=Path)
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--tokenizer-mode", choices=("model", "whitespace"), default="whitespace")
    parser.add_argument("--max-seq-length", type=int, required=True)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=1)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--num-train-epochs", type=int, default=1)
    parser.add_argument("--packing", action="store_true")
    parser.add_argument("--serious", action="store_true")
    parser.add_argument("--min-records", type=int, default=1000)
    parser.add_argument("--min-target-tokens", type=int, default=1_000_000)
    parser.add_argument("--gpu-vram-gb", type=float)
    parser.add_argument("--model-tier")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.tokenizer_mode == "model" and args.model_config is None:
        parser.error("--model-config is required when --tokenizer-mode=model")
    tokenizer = (
        load_tokenizer_from_model_config(args.model_config, tokenizer_mode=args.tokenizer_mode)
        if args.model_config
        else None
    )
    train_stats = compute_jsonl_accounting(
        args.train_file,
        tokenizer=tokenizer,
        max_seq_length=args.max_seq_length,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        max_steps=args.max_steps,
        num_train_epochs=args.num_train_epochs,
        packing=args.packing,
    )
    validation_stats = None
    if args.validation_file:
        validation_stats = compute_jsonl_accounting(
            args.validation_file,
            tokenizer=tokenizer,
            max_seq_length=args.max_seq_length,
            per_device_train_batch_size=args.per_device_train_batch_size,
            gradient_accumulation_steps=args.gradient_accumulation_steps,
            max_steps=args.max_steps,
            num_train_epochs=args.num_train_epochs,
            packing=args.packing,
        )

    payload: dict[str, Any] = {
        "train": train_stats.as_dict(),
        "validation": validation_stats.as_dict() if validation_stats else None,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    if args.serious:
        errors = validate_serious_gates(
            train_stats,
            validation_record_count=validation_stats.record_count if validation_stats else 0,
            min_records=args.min_records,
            min_target_tokens=args.min_target_tokens,
            max_seq_length=args.max_seq_length,
            gpu_vram_gb=args.gpu_vram_gb,
            model_tier=args.model_tier,
        )
        if errors:
            for error in errors:
                print(error)
            return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
