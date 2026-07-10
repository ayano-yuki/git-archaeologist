from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run model evaluation prompts.")
    parser.add_argument("--prompts", type=Path, default=Path("evals/prompts/smoke.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("evals/results/smoke.jsonl"))
    args = parser.parse_args()

    raise NotImplementedError(
        "Add inference backend integration for the model serving target."
        f" Received: {args}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
