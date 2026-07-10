from __future__ import annotations

import argparse
from pathlib import Path

from llm_tuning_lab.data.github_sft import (
    build_sft_records,
    load_github_records,
    split_train_validation,
    write_sft_jsonl,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare raw data for fine-tuning.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Backward-compatible alias for --train-output.")
    parser.add_argument("--train-output", type=Path, default=Path("data/processed/train.jsonl"))
    parser.add_argument("--validation-output", type=Path, default=Path("data/processed/validation.jsonl"))
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--max-records", type=int)
    args = parser.parse_args()

    train_output = args.output or args.train_output
    raw_records = load_github_records(args.input)
    sft_records = build_sft_records(raw_records, max_records=args.max_records)
    train_records, validation_records = split_train_validation(
        sft_records,
        validation_ratio=args.validation_ratio,
    )

    train_count = write_sft_jsonl(train_output, train_records)
    validation_count = write_sft_jsonl(args.validation_output, validation_records)

    print(f"raw_records: {len(raw_records)}")
    print(f"sft_records: {len(sft_records)}")
    print(f"train: {train_count} -> {train_output}")
    print(f"validation: {validation_count} -> {args.validation_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
