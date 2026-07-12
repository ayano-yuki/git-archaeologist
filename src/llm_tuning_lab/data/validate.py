from __future__ import annotations

import argparse
import json
from pathlib import Path

from llm_tuning_lab.data.formatters import validate_messages_record, validate_preference_record


VALIDATORS = {
    "messages": validate_messages_record,
    "dpo": validate_preference_record,
    "preference": validate_preference_record,
}


def validate_jsonl(path: Path, *, data_format: str = "messages") -> list[str]:
    errors: list[str] = []
    validator = VALIDATORS[data_format]

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_number}: invalid JSON: {exc.msg}")
                continue

            if not isinstance(record, dict):
                errors.append(f"{path}:{line_number}: record must be a JSON object")
                continue

            for error in validator(record):
                errors.append(f"{path}:{line_number}: {error}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate fine-tuning JSONL data.")
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--format",
        choices=sorted(VALIDATORS),
        default="messages",
        help="JSONL format to validate.",
    )
    args = parser.parse_args()

    errors = validate_jsonl(args.path, data_format=args.format)
    if errors:
        for error in errors:
            print(error)
        return 1

    print(f"OK: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
