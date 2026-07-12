from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any


def write_training_manifest(
    output_dir: Path,
    *,
    model_config: dict[str, Any],
    data_config: dict[str, Any],
    train_config: dict[str, Any],
    lora_config: dict[str, Any] | None = None,
    parent_sft_adapter: str | None = None,
    parent_manifest_hash: str | None = None,
    accounting: dict[str, Any] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    config_payload: dict[str, Any] = {
        "model": model_config,
        "data": data_config,
        "train": train_config,
    }
    if lora_config is not None:
        config_payload["lora"] = lora_config
    if parent_sft_adapter is not None:
        config_payload["parent_sft_adapter"] = parent_sft_adapter
        config_payload["parent_manifest_hash"] = parent_manifest_hash

    manifest = {
        "manifest_schema_version": 2,
        "base_model": model_config.get("model_name_or_path"),
        "model_revision": model_config.get("revision"),
        "dataset_hash": _dataset_hash(data_config),
        "git_commit": _git_commit(),
        "config_hash": _hash_json(config_payload),
        "versions": _package_versions(
            "transformers",
            "trl",
            "peft",
            "torch",
            "datasets",
            "bitsandbytes",
        ),
        "runtime": _runtime_info(),
        "seed": train_config.get("seed"),
        "effective_batch_size": (
            int(train_config.get("per_device_train_batch_size", 1))
            * int(train_config.get("gradient_accumulation_steps", 1))
        ),
        "splits": _split_counts(data_config),
    }
    if lora_config is not None:
        manifest["lora_config"] = lora_config
    if parent_sft_adapter is not None:
        manifest["parent_sft_adapter"] = parent_sft_adapter
        manifest["parent_manifest_hash"] = parent_manifest_hash
    if accounting is not None:
        manifest["accounting"] = accounting
    path = output_dir / "training_manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def training_manifest_hash(adapter_path: Path | str) -> str | None:
    manifest_path = Path(adapter_path) / "training_manifest.json"
    if not manifest_path.exists() or not manifest_path.is_file():
        return None
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def _dataset_hash(data_config: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for key in ("train_file", "validation_file", "test_file"):
        value = data_config.get(key)
        if not value:
            continue
        path = Path(str(value))
        digest.update(str(path).encode("utf-8"))
        if path.exists() and path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _split_counts(data_config: dict[str, Any]) -> dict[str, int | None]:
    return {
        "train": _count_jsonl(data_config.get("train_file")),
        "validation": _count_jsonl(data_config.get("validation_file")),
        "test": _count_jsonl(data_config.get("test_file")),
    }


def _count_jsonl(value: Any) -> int | None:
    if not value:
        return None
    path = Path(str(value))
    if not path.exists() or not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _package_versions(*names: str) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _runtime_info() -> dict[str, Any]:
    info: dict[str, Any] = {"python": platform.python_version(), "platform": platform.platform()}
    try:
        import torch

        info["cuda_version"] = getattr(torch.version, "cuda", None)
        info["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except ImportError:
        info["cuda_version"] = None
        info["gpu"] = None
    return info


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _hash_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
