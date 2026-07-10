from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from llm_tuning_lab.data.bundles import read_jsonl, write_jsonl

SYSTEM_PROMPT = (
    "You are Git Archaeologist. Use repository evidence first, separate facts from "
    "inference, cite evidence IDs, and explain uncertainty."
)

CONFIDENT_TERMS = ("proves", "definitely", "certainly", "明らか", "断定", "証明")
REVIEW_STATUSES = {"draft", "approved", "rejected"}
APPROVED_REVIEW_FIELDS = ("reviewer_id", "reviewed_at", "review_revision", "bundle_hash", "evidence_hash")
OUTPUT_SCHEMA_VERSION = "git-archaeologist.answer.v1"
APPROX_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class GoldValidationResult:
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def load_bundles(path: Path) -> dict[str, dict[str, Any]]:
    return {str(bundle["bundle_id"]): bundle for bundle in read_jsonl(path)}


def load_gold_cases(path: Path) -> list[dict[str, Any]]:
    return list(read_jsonl(path))


def validate_gold_cases(
    bundles: dict[str, dict[str, Any]],
    cases: Iterable[dict[str, Any]],
) -> GoldValidationResult:
    errors: list[str] = []
    for index, case in enumerate(cases, start=1):
        errors.extend(_validate_gold_case(index, bundles, case))
    return GoldValidationResult(errors)


def materialize_sft_records(
    bundles: dict[str, dict[str, Any]],
    cases: Iterable[dict[str, Any]],
    *,
    require_approved: bool = True,
    max_seq_length: int | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case in cases:
        if require_approved and case.get("review_status") != "approved":
            continue
        bundle = bundles[str(case["bundle_id"])]
        record = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_content(bundle, case)},
                {"role": "assistant", "content": _assistant_content(case)},
            ]
        }
        if max_seq_length is not None:
            errors = validate_sft_record_budget(record, case, max_seq_length=max_seq_length)
            if errors:
                raise ValueError("; ".join(errors))
        records.append(record)
    return records


def split_gold_cases(
    bundles: dict[str, dict[str, Any]],
    cases: Iterable[dict[str, Any]],
    *,
    validation_ratio: float = 0.1,
    test_ratio: float = 0.1,
    split_strategy: str = "thread_hash",
    validation_repositories: list[str] | None = None,
    test_repositories: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    splits = {"train": [], "validation": [], "test": []}
    if split_strategy == "repository_holdout":
        validation_set = set(validation_repositories or [])
        test_set = set(test_repositories or [])
        overlap = validation_set & test_set
        if overlap:
            raise ValueError(f"repositories cannot be in both validation and test: {sorted(overlap)}")
        for case in cases:
            bundle = bundles[str(case["bundle_id"])]
            repo = str(bundle["repo"])
            if repo in test_set:
                split = "test"
            elif repo in validation_set:
                split = "validation"
            else:
                split = "train"
            splits[split].append(case)
        return splits
    if split_strategy != "thread_hash":
        raise ValueError(f"unknown split strategy: {split_strategy}")

    validation_ratio = _clamp_ratio(validation_ratio)
    test_ratio = _clamp_ratio(test_ratio)
    groups: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        bundle = bundles[str(case["bundle_id"])]
        group_key = f"{bundle['repo']}:{bundle['thread_key']}"
        groups.setdefault(group_key, []).append(case)

    ordered_groups = sorted(groups.items(), key=lambda item: (_hash_fraction(item[0]), item[0]))
    group_count = len(ordered_groups)
    test_count, validation_count = _holdout_counts(group_count, validation_ratio, test_ratio)
    for index, (_, group_cases) in enumerate(ordered_groups):
        if index < test_count:
            split = "test"
        elif index < test_count + validation_count:
            split = "validation"
        else:
            split = "train"
        splits[split].extend(group_cases)
    return splits


def write_materialized_splits(
    bundles: dict[str, dict[str, Any]],
    cases: list[dict[str, Any]],
    *,
    train_output: Path,
    validation_output: Path,
    test_output: Path,
    benchmark_output: Path,
    validation_ratio: float,
    test_ratio: float,
    require_approved: bool,
    max_seq_length: int,
    split_strategy: str = "thread_hash",
    validation_repositories: list[str] | None = None,
    test_repositories: list[str] | None = None,
) -> dict[str, int]:
    approved_cases = [
        case for case in cases if not require_approved or case.get("review_status") == "approved"
    ]
    splits = split_gold_cases(
        bundles,
        approved_cases,
        validation_ratio=validation_ratio,
        test_ratio=test_ratio,
        split_strategy=split_strategy,
        validation_repositories=validation_repositories,
        test_repositories=test_repositories,
    )
    counts = {
        "train": write_jsonl(
            train_output,
            materialize_sft_records(bundles, splits["train"], max_seq_length=max_seq_length),
        ),
        "validation": write_jsonl(
            validation_output,
            materialize_sft_records(
                bundles,
                splits["validation"],
                max_seq_length=max_seq_length,
            ),
        ),
        "test": write_jsonl(
            test_output,
            materialize_sft_records(bundles, splits["test"], max_seq_length=max_seq_length),
        ),
        "benchmark": write_jsonl(benchmark_output, _benchmark_records(bundles, splits["test"])),
    }
    return counts


def bundle_hash(bundle: dict[str, Any]) -> str:
    payload = {
        "bundle_id": bundle.get("bundle_id"),
        "repo": bundle.get("repo"),
        "thread_key": bundle.get("thread_key"),
        "evidence": bundle.get("evidence", []),
    }
    return _hash_json(payload)


def evidence_hash(bundle: dict[str, Any]) -> str:
    return _hash_json(bundle.get("evidence", []))


def validate_sft_record_budget(
    record: dict[str, Any],
    case: dict[str, Any],
    *,
    max_seq_length: int,
) -> list[str]:
    errors: list[str] = []
    content = "\n".join(message.get("content", "") for message in record.get("messages", []))
    estimated_tokens = _estimate_tokens(content)
    if estimated_tokens > max_seq_length:
        errors.append(
            f"case {case.get('bundle_id')}: estimated tokens {estimated_tokens} exceed max_seq_length {max_seq_length}"
        )
    user_content = record["messages"][1]["content"]
    for citation in _citation_ids(case.get("citations")):
        if citation not in user_content:
            errors.append(f"case {case.get('bundle_id')}: cited evidence {citation} missing from SFT input")
    return errors


def _validate_gold_case(
    index: int,
    bundles: dict[str, dict[str, Any]],
    case: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    prefix = f"case {index}"
    required = (
        "bundle_id",
        "question",
        "answer",
        "facts",
        "timeline",
        "inference",
        "uncertainty",
        "citations",
        "review_status",
    )
    for field in required:
        if field not in case:
            errors.append(f"{prefix}: missing required field '{field}'")
    if errors:
        return errors

    bundle = bundles.get(str(case["bundle_id"]))
    if bundle is None:
        return [f"{prefix}: unknown bundle_id '{case['bundle_id']}'"]

    evidence_ids = {str(item["evidence_id"]) for item in bundle.get("evidence", [])}
    citations = _citation_ids(case.get("citations"))
    unknown = sorted(citations - evidence_ids)
    if unknown:
        errors.append(f"{prefix}: citations not found in bundle evidence: {', '.join(unknown)}")
    if not citations:
        errors.append(f"{prefix}: citations must not be empty")
    review_status = case.get("review_status")
    if review_status not in REVIEW_STATUSES:
        errors.append(f"{prefix}: review_status must be one of {sorted(REVIEW_STATUSES)}")
    if review_status == "approved":
        for field in APPROVED_REVIEW_FIELDS:
            if not str(case.get(field) or "").strip():
                errors.append(f"{prefix}: approved case must define '{field}'")
        if str(case.get("bundle_hash") or "") != bundle_hash(bundle):
            errors.append(f"{prefix}: bundle_hash does not match current bundle")
        if str(case.get("evidence_hash") or "") != evidence_hash(bundle):
            errors.append(f"{prefix}: evidence_hash does not match current bundle evidence")
        if _parse_datetime(case.get("reviewed_at")) is None:
            errors.append(f"{prefix}: reviewed_at must be an ISO datetime")

    errors.extend(_validate_facts(prefix, case.get("facts"), evidence_ids))
    errors.extend(_validate_timeline(prefix, case.get("timeline"), evidence_ids))
    if not str(case.get("uncertainty") or "").strip():
        errors.append(f"{prefix}: uncertainty must not be empty")
    if _single_evidence_assertion(case, citations):
        errors.append(f"{prefix}: single-evidence confident assertion is not allowed")
    return errors


def _validate_facts(prefix: str, facts: Any, evidence_ids: set[str]) -> list[str]:
    if not isinstance(facts, list) or not facts:
        return [f"{prefix}: facts must be a non-empty list"]
    errors: list[str] = []
    for item_index, fact in enumerate(facts, start=1):
        if not isinstance(fact, dict):
            errors.append(f"{prefix}: facts[{item_index}] must include text and citations")
            continue
        if not str(fact.get("text") or "").strip():
            errors.append(f"{prefix}: facts[{item_index}].text must not be empty")
        citations = _citation_ids(fact.get("citations"))
        if not citations:
            errors.append(f"{prefix}: facts[{item_index}] must cite evidence")
        unknown = sorted(citations - evidence_ids)
        if unknown:
            errors.append(f"{prefix}: facts[{item_index}] cites unknown evidence: {', '.join(unknown)}")
    return errors


def _validate_timeline(prefix: str, timeline: Any, evidence_ids: set[str]) -> list[str]:
    if not isinstance(timeline, list):
        return [f"{prefix}: timeline must be a list"]
    if not timeline:
        return [f"{prefix}: timeline must be a non-empty list"]
    errors: list[str] = []
    previous: datetime | None = None
    for item_index, item in enumerate(timeline, start=1):
        if not isinstance(item, dict):
            errors.append(f"{prefix}: timeline[{item_index}] must be an object")
            continue
        if not str(item.get("text") or "").strip():
            errors.append(f"{prefix}: timeline[{item_index}].text must not be empty")
        citations = _citation_ids(item.get("citations"))
        if not citations:
            errors.append(f"{prefix}: timeline[{item_index}] must cite evidence")
        if citations - evidence_ids:
            errors.append(f"{prefix}: timeline[{item_index}] cites unknown evidence")
        when = _parse_datetime(item.get("date") or item.get("created_at"))
        if when is None:
            continue
        if previous is not None and when < previous:
            errors.append(f"{prefix}: timeline is not chronological")
            break
        previous = when
    return errors


def _benchmark_records(
    bundles: dict[str, dict[str, Any]],
    cases: list[dict[str, Any]],
) -> Iterable[dict[str, Any]]:
    for case in cases:
        bundle = bundles[str(case["bundle_id"])]
        yield {
            "id": str(case["bundle_id"]),
            "bundle": bundle,
            "question": case["question"],
            "expected": {
                "facts": case["facts"],
                "citations": case["citations"],
                "timeline": case["timeline"],
                "inference": case["inference"],
                "uncertainty": case["uncertainty"],
                "answer": case["answer"],
            },
        }


def _user_content(bundle: dict[str, Any], case: dict[str, Any]) -> str:
    evidence_lines = []
    for item in bundle.get("evidence", []):
        evidence_lines.append(
            f"[{item['evidence_id']}] {item['kind']} {item.get('source_id')}: {item['summary']}"
        )
    return (
        f"Repository: {bundle['repo']}\n"
        f"Thread: {bundle['thread_key']}\n"
        f"Question: {case['question']}\n\n"
        "Evidence:\n"
        + "\n".join(evidence_lines)
    )


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


def _citation_ids(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    citations: set[str] = set()
    for item in value:
        if isinstance(item, str):
            citations.add(item)
        elif isinstance(item, dict) and item.get("evidence_id"):
            citations.add(str(item["evidence_id"]))
    return citations


def _single_evidence_assertion(case: dict[str, Any], citations: set[str]) -> bool:
    if len(citations) > 1:
        return False
    text = " ".join(str(case.get(key) or "") for key in ("answer", "inference"))
    lowered = text.lower()
    return any(term.lower() in lowered for term in CONFIDENT_TERMS)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hash_fraction(value: str) -> float:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _estimate_tokens(value: str) -> int:
    return max(1, (len(value) + APPROX_CHARS_PER_TOKEN - 1) // APPROX_CHARS_PER_TOKEN)


def _clamp_ratio(value: float) -> float:
    return min(max(float(value), 0.0), 0.5)


def _holdout_counts(
    group_count: int,
    validation_ratio: float,
    test_ratio: float,
) -> tuple[int, int]:
    if group_count <= 1:
        return 0, 0
    test_count = max(1, round(group_count * test_ratio)) if test_ratio > 0 and group_count >= 3 else 0
    remaining_after_test = group_count - test_count
    validation_count = (
        max(1, round(group_count * validation_ratio))
        if validation_ratio > 0 and remaining_after_test >= 2
        else 0
    )
    while test_count + validation_count >= group_count:
        if validation_count > 0:
            validation_count -= 1
        elif test_count > 0:
            test_count -= 1
    return test_count, validation_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and materialize Git Archaeologist gold cases.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--bundles", type=Path, required=True)
    validate_parser.add_argument("--gold-cases", type=Path, required=True)

    materialize_parser = subparsers.add_parser("materialize")
    materialize_parser.add_argument("--bundles", type=Path, required=True)
    materialize_parser.add_argument("--gold-cases", type=Path, required=True)
    materialize_parser.add_argument("--train-output", type=Path, required=True)
    materialize_parser.add_argument("--validation-output", type=Path, required=True)
    materialize_parser.add_argument("--test-output", type=Path, required=True)
    materialize_parser.add_argument("--benchmark-output", type=Path, required=True)
    materialize_parser.add_argument("--validation-ratio", type=float, default=0.1)
    materialize_parser.add_argument("--test-ratio", type=float, default=0.1)
    materialize_parser.add_argument("--max-seq-length", type=int, default=2048)
    materialize_parser.add_argument(
        "--split-strategy",
        choices=("thread_hash", "repository_holdout"),
        default="thread_hash",
    )
    materialize_parser.add_argument("--validation-repository", action="append", default=[])
    materialize_parser.add_argument("--test-repository", action="append", default=[])
    materialize_parser.add_argument("--allow-unapproved", action="store_true")
    args = parser.parse_args()

    bundles = load_bundles(args.bundles)
    cases = load_gold_cases(args.gold_cases)
    result = validate_gold_cases(bundles, cases)
    if not result.ok:
        for error in result.errors:
            print(error)
        return 1
    if args.command == "validate":
        print(f"OK: {args.gold_cases}")
        return 0

    counts = write_materialized_splits(
        bundles,
        cases,
        train_output=args.train_output,
        validation_output=args.validation_output,
        test_output=args.test_output,
        benchmark_output=args.benchmark_output,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
        require_approved=not args.allow_unapproved,
        max_seq_length=args.max_seq_length,
        split_strategy=args.split_strategy,
        validation_repositories=args.validation_repository,
        test_repositories=args.test_repository,
    )
    for name, count in counts.items():
        print(f"{name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
