from __future__ import annotations

import argparse
import json
from pathlib import Path

from llm_tuning_lab.data.formatters import validate_messages_record


def validate_jsonl(path: Path) -> list[str]:
    errors: list[str] = []

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

            for error in validate_messages_record(record):
                errors.append(f"{path}:{line_number}: {error}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate chat-style SFT JSONL data.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    errors = validate_jsonl(args.path)
    if errors:
        for error in errors:
            print(error)
        return 1

    print(f"OK: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
