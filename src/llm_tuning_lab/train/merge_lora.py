from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge a LoRA adapter into a base model.")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raise NotImplementedError(
        "Add PEFT merge_and_unload flow when the base model and adapter format are confirmed."
        f" Received: {args}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
