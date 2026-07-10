from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run preference tuning with DPO.")
    parser.add_argument("--model-config", type=Path, default=Path("configs/model/base.yaml"))
    parser.add_argument("--data-config", type=Path, required=True)
    parser.add_argument("--train-config", type=Path, default=Path("configs/train/dpo.yaml"))
    args = parser.parse_args()

    raise NotImplementedError(
        "Wire this entry point to TRL DPOTrainer after preparing preference data."
        f" Received: {args}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
