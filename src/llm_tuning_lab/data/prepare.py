from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare raw data for fine-tuning.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raise NotImplementedError(
        f"Add project-specific conversion from {args.input} to {args.output}."
    )


if __name__ == "__main__":
    raise SystemExit(main())
