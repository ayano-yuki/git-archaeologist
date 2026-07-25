"""Utilities for reviewed SFT JSONL datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from git_archaeologist.evaluation.sft_data_policy import SFTRecord, Split, validate_sft_record


@dataclass(frozen=True)
class SFTDatasetReport:
    """Validation summary for a reviewed SFT dataset."""

    path: str
    record_count: int
    split_counts: dict[str, int]
    record_ids: tuple[str, ...]


def load_sft_jsonl(path: Path) -> tuple[SFTRecord, ...]:
    """Load and validate reviewed SFT records from JSONL."""

    records: list[SFTRecord] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw_record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
        records.append(validate_sft_record(raw_record))
    if not records:
        raise ValueError("SFT dataset must contain at least one reviewed record")
    _ensure_unique_record_ids(tuple(records))
    return tuple(records)


def validate_sft_dataset(path: Path) -> SFTDatasetReport:
    """Validate an SFT dataset and return split counts."""

    records = load_sft_jsonl(path)
    split_counts = {split.value: 0 for split in Split}
    for record in records:
        split_counts[record.split.value] += 1
    return SFTDatasetReport(
        path=str(path),
        record_count=len(records),
        split_counts=split_counts,
        record_ids=tuple(record.record_id for record in records),
    )


def _ensure_unique_record_ids(records: tuple[SFTRecord, ...]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for record in records:
        if record.record_id in seen:
            duplicates.append(record.record_id)
        seen.add(record.record_id)
    if duplicates:
        raise ValueError(f"duplicate SFT record IDs: {', '.join(sorted(duplicates))}")
