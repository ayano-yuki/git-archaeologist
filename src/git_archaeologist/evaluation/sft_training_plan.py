"""LoRA/QLoRA training plan records tied to the Phase2 SFT decision."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


SFT_TRAINING_PLAN_SCHEMA_VERSION = 1


class SFTTrainingStatus(StrEnum):
    """Whether training should run for the current evaluation state."""

    READY = "ready"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class SFTTrainingPlan:
    """Reproducible SFT run plan or a recorded deferral."""

    schema_version: int
    status: SFTTrainingStatus
    method: str
    base_model: str
    dataset_path: str
    output_dir: str
    seed: int
    reason: str
    training_args: Mapping[str, object]
    safety_checks: tuple[str, ...]

    @property
    def should_train(self) -> bool:
        return self.status is SFTTrainingStatus.READY


def build_sft_training_plan(
    decision_record: Mapping[str, object],
    *,
    dataset_path: Path,
    output_dir: Path,
    base_model: str,
    method: str = "qlora",
    seed: int = 20260726,
) -> SFTTrainingPlan:
    """Build a training plan that respects the Phase2 SFT decision."""

    decision = str(decision_record.get("decision", ""))
    if decision != "consider_sft":
        return SFTTrainingPlan(
            schema_version=SFT_TRAINING_PLAN_SCHEMA_VERSION,
            status=SFTTrainingStatus.DEFERRED,
            method=method,
            base_model=base_model,
            dataset_path=str(dataset_path),
            output_dir=str(output_dir),
            seed=seed,
            reason=f"SFT decision is {decision or 'unknown'}, so adapter training is deferred.",
            training_args=MappingProxyType({}),
            safety_checks=(),
        )
    return SFTTrainingPlan(
        schema_version=SFT_TRAINING_PLAN_SCHEMA_VERSION,
        status=SFTTrainingStatus.READY,
        method=method,
        base_model=base_model,
        dataset_path=str(dataset_path),
        output_dir=str(output_dir),
        seed=seed,
        reason="Evaluation shows repeated answer-discipline failures after RAG improvements.",
        training_args=MappingProxyType({}),
        safety_checks=(),
    )


def load_sft_training_plan(path: Path) -> SFTTrainingPlan:
    """Load a recorded SFT training plan from JSON."""

    try:
        raw_plan = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid SFT training plan JSON: {path}") from exc
    if not isinstance(raw_plan, Mapping):
        raise ValueError("SFT training plan must be a JSON object")

    schema_version = _require_int(raw_plan, "schema_version")
    if schema_version != SFT_TRAINING_PLAN_SCHEMA_VERSION:
        raise ValueError(f"unsupported SFT training plan schema_version: {schema_version}")

    training_args = raw_plan.get("training_args", {})
    if not isinstance(training_args, Mapping):
        raise ValueError("training_args must be an object")

    safety_checks = raw_plan.get("safety_checks", ())
    if not isinstance(safety_checks, list | tuple) or not all(
        isinstance(check, str) for check in safety_checks
    ):
        raise ValueError("safety_checks must be a list of strings")

    return SFTTrainingPlan(
        schema_version=schema_version,
        status=SFTTrainingStatus(_require_str(raw_plan, "status")),
        method=_require_str(raw_plan, "method"),
        base_model=_require_str(raw_plan, "base_model"),
        dataset_path=_require_str(raw_plan, "dataset_path"),
        output_dir=_require_str(raw_plan, "output_dir"),
        seed=_require_int(raw_plan, "seed"),
        reason=_require_str(raw_plan, "reason"),
        training_args=MappingProxyType(dict(training_args)),
        safety_checks=tuple(safety_checks),
    )


def sft_training_plan_to_dict(plan: SFTTrainingPlan) -> dict[str, object]:
    """Return a JSON-friendly representation of an SFT training plan."""

    return {
        "schema_version": plan.schema_version,
        "status": plan.status.value,
        "method": plan.method,
        "base_model": plan.base_model,
        "dataset_path": plan.dataset_path,
        "output_dir": plan.output_dir,
        "seed": plan.seed,
        "reason": plan.reason,
        "training_args": dict(plan.training_args),
        "safety_checks": list(plan.safety_checks),
    }


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = _require(raw, key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    value = _require(raw, key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _require(raw: Mapping[str, Any], key: str) -> Any:
    if key not in raw:
        raise ValueError(f"missing required field: {key}")
    return raw[key]
