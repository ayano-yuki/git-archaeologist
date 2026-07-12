from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from llm_tuning_lab.data.bundles import write_jsonl
from llm_tuning_lab.data.gold_cases import (
    load_bundles,
    load_gold_cases,
    split_gold_cases,
    validate_gold_cases,
    validate_sft_record_budget,
)

SYSTEM_PROMPT = (
    "You are Git Archaeologist. Use retrieved repository evidence first, ignore irrelevant "
    "evidence, separate facts from inference, cite evidence IDs, and explain uncertainty."
)
OUTPUT_SCHEMA_VERSION = "git-archaeologist.answer.v1"


def materialize_raft_records(
    bundles: dict[str, dict[str, Any]],
    cases: Iterable[dict[str, Any]],
    *,
    distractors_per_record: int = 2,
    require_approved: bool = True,
    max_seq_length: int | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case in _eligible_cases(cases, require_approved=require_approved):
        bundle = bundles[str(case["bundle_id"])]
        distractors = _distractor_evidence(bundles, bundle, distractors_per_record)
        record = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _prompt_content(bundle, case, distractors)},
                {"role": "assistant", "content": _assistant_content(case)},
            ]
        }
        if max_seq_length is not None:
            errors = validate_sft_record_budget(record, case, max_seq_length=max_seq_length)
            if errors:
                raise ValueError("; ".join(errors))
        records.append(record)
    return records


def materialize_dpo_records(
    bundles: dict[str, dict[str, Any]],
    cases: Iterable[dict[str, Any]],
    *,
    distractors_per_record: int = 2,
    require_approved: bool = True,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case in _eligible_cases(cases, require_approved=require_approved):
        bundle = bundles[str(case["bundle_id"])]
        distractors = _distractor_evidence(bundles, bundle, distractors_per_record)
        prompt = _prompt_content(bundle, case, distractors)
        records.append(
            {
                "prompt": _dpo_prompt_content(prompt),
                "chosen": str(case.get("chosen") or _assistant_content(case)),
                "rejected": str(case.get("rejected") or case.get("rejected_answer") or _rejected_content(case)),
            }
        )
    return records


def _eligible_cases(
    cases: Iterable[dict[str, Any]],
    *,
    require_approved: bool,
) -> Iterable[dict[str, Any]]:
    for case in cases:
        if require_approved and case.get("review_status") != "approved":
            continue
        yield case


def _prompt_content(
    bundle: dict[str, Any],
    case: dict[str, Any],
    distractors: list[dict[str, Any]],
) -> str:
    evidence = list(bundle.get("evidence", [])) + distractors
    evidence = sorted(evidence, key=lambda item: str(item.get("evidence_id") or ""))
    lines = [
        f"[{item['evidence_id']}] {item.get('kind')} {item.get('source_id')}: {item.get('summary')}"
        for item in evidence
    ]
    return (
        f"Repository: {bundle['repo']}\n"
        f"Thread: {bundle['thread_key']}\n"
        f"Question: {case['question']}\n\n"
        "Retrieved evidence. Some items may be irrelevant, outdated, or only weakly related:\n"
        + "\n".join(lines)
    )


def _dpo_prompt_content(user_prompt: str) -> str:
    return f"System: {SYSTEM_PROMPT}\n\nUser:\n{user_prompt}"


def _assistant_content(case: dict[str, Any]) -> str:
    return json.dumps(
        {
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "facts": case["facts"],
            "timeline": case["timeline"],
            "inference": case["inference"],
            "uncertainty": case["uncertainty"],
            "citations": case["citations"],
            "answer": case["answer"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _rejected_content(case: dict[str, Any]) -> str:
    return json.dumps(
        {
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "facts": [],
            "timeline": [],
            "inference": "This was definitely the intended design based on the visible discussion.",
            "uncertainty": "",
            "citations": [],
            "answer": (
                "The change was clearly intentional and safe. The repository history proves it, "
                f"so no additional checks are needed for: {case['question']}"
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _distractor_evidence(
    bundles: dict[str, dict[str, Any]],
    target_bundle: dict[str, Any],
    count: int,
) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    candidates: list[dict[str, Any]] = []
    target_id = str(target_bundle["bundle_id"])
    for bundle in bundles.values():
        if str(bundle.get("bundle_id")) == target_id:
            continue
        candidates.extend(bundle.get("evidence", []))
    return sorted(
        candidates,
        key=lambda item: _stable_fraction(target_id, str(item.get("evidence_id") or "")),
    )[:count]


def _stable_fraction(*parts: str) -> float:
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize Git Archaeologist roadmap data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("raft", "dpo"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--bundles", type=Path, required=True)
        subparser.add_argument("--gold-cases", type=Path, required=True)
        subparser.add_argument("--output", type=Path)
        subparser.add_argument("--train-output", type=Path)
        subparser.add_argument("--validation-output", type=Path)
        subparser.add_argument("--validation-ratio", type=float, default=0.1)
        subparser.add_argument("--distractors-per-record", type=int, default=2)
        subparser.add_argument("--allow-unapproved", action="store_true")
        if name == "raft":
            subparser.add_argument("--max-seq-length", type=int, default=2048)

    args = parser.parse_args()
    bundles = load_bundles(args.bundles)
    cases = load_gold_cases(args.gold_cases)
    result = validate_gold_cases(bundles, cases)
    if not result.ok:
        for error in result.errors:
            print(error)
        return 1
    if not args.output and not (args.train_output and args.validation_output):
        parser.error("provide --output or both --train-output and --validation-output")

    common_args = {
        "distractors_per_record": args.distractors_per_record,
        "require_approved": not args.allow_unapproved,
    }
    materializer = materialize_raft_records if args.command == "raft" else materialize_dpo_records
    materializer_args = dict(common_args)
    if args.command == "raft":
        materializer_args["max_seq_length"] = args.max_seq_length

    if args.train_output and args.validation_output:
        eligible_cases = list(
            _eligible_cases(cases, require_approved=not args.allow_unapproved)
        )
        splits = split_gold_cases(
            bundles,
            eligible_cases,
            validation_ratio=args.validation_ratio,
            test_ratio=0.0,
        )
        _require_non_empty_validation_split(splits["validation"])
        train_records = materializer(
            bundles,
            splits["train"],
            **{**materializer_args, "require_approved": False},
        )
        validation_records = materializer(
            bundles,
            splits["validation"],
            **{**materializer_args, "require_approved": False},
        )
        train_count = write_jsonl(args.train_output, train_records)
        validation_count = write_jsonl(args.validation_output, validation_records)
        print(f"train: {train_count} -> {args.train_output}")
        print(f"validation: {validation_count} -> {args.validation_output}")
        return 0

    if args.command == "raft":
        records = materialize_raft_records(
            bundles,
            cases,
            max_seq_length=args.max_seq_length,
            **common_args,
        )
    else:
        records = materialize_dpo_records(bundles, cases, **common_args)

    count = write_jsonl(args.output, records)
    print(f"{args.command}: {count} -> {args.output}")
    return 0


def _require_non_empty_validation_split(validation_cases: list[dict[str, Any]]) -> None:
    if validation_cases:
        return
    raise ValueError(
        "roadmap split output requires a non-empty validation split; "
        "add more approved gold cases or increase --validation-ratio"
    )


if __name__ == "__main__":
    raise SystemExit(main())
