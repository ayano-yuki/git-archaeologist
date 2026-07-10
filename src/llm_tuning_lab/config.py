from __future__ import annotations

from pathlib import Path
from typing import Any


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to read config files.") from exc

    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}

    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML object.")

    return loaded


def override_if_set(config: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    if value is not None:
        config[key] = value
    return config
