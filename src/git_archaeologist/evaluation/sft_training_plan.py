"""LoRA/QLoRA training plan records tied to the Phase2 SFT decision."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping


class SFTTrainingStatus(StrEnum):
    """Whether training should run for the current evaluation state."""

    READY = "ready"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class SFTTrainingPlan:
    """Reproducible SFT run plan or a recorded deferral."""

    status: SFTTrainingStatus
    method: str
    base_model: str
    dataset_path: str
    output_dir: str
    seed: int
    reason: str

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
            status=SFTTrainingStatus.DEFERRED,
            method=method,
            base_model=base_model,
            dataset_path=str(dataset_path),
            output_dir=str(output_dir),
            seed=seed,
            reason=f"SFT decision is {decision or 'unknown'}, so adapter training is deferred.",
        )
    return SFTTrainingPlan(
        status=SFTTrainingStatus.READY,
        method=method,
        base_model=base_model,
        dataset_path=str(dataset_path),
        output_dir=str(output_dir),
        seed=seed,
        reason="Evaluation shows repeated answer-discipline failures after RAG improvements.",
    )
