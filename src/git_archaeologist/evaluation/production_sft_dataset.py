"""Build production SFT records from the local raw GitHub archive."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from git_archaeologist.evaluation.sft_data_policy import validate_sft_record
from git_archaeologist.evaluation.sft_dataset import validate_sft_dataset


REPOSITORY_ID = "react/react"
BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
MODEL_DATA_DIR = "Qwen--Qwen2.5-Coder-7B-Instruct"
DEFAULT_RAW_ROOT = Path("data/local-runtime/raw/react/react")
DEFAULT_DATASET_PATH = Path(
    f"data/{MODEL_DATA_DIR}/sft/answer-discipline/production-sft-records.jsonl"
)
DEFAULT_PLAN_PATH = Path(
    f"data/{MODEL_DATA_DIR}/sft/answer-discipline/production-lora-training-plan.json"
)
DEFAULT_OUTPUT_DIR = Path(f"data/{MODEL_DATA_DIR}/models/answer-discipline-qlora")
DEFAULT_SUMMARY_PATH = Path(
    f"data/{MODEL_DATA_DIR}/sft/answer-discipline/production-sft-summary.json"
)

TASK_BY_KIND = {
    "commit": "implementation_rationale",
    "pull_request": "implementation_rationale",
    "issue": "issue_triage",
    "issue_comment": "issue_triage",
    "review": "review_judgment",
    "review_comment": "review_judgment",
    "ci_run": "risk_judgment",
    "ci_job": "risk_judgment",
}


@dataclass(frozen=True)
class ProductionSFTBuildSummary:
    """Summary for a generated production SFT dataset."""

    status: str
    raw_root: str
    dataset_path: str
    plan_path: str
    summary_path: str
    raw_artifact_count: int
    record_count: int
    split_counts: dict[str, int]
    artifact_counts: dict[str, int]
    decision_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_production_sft_records(raw_root: Path = DEFAULT_RAW_ROOT) -> tuple[dict[str, object], ...]:
    """Build validated SFT records from production raw archive files."""

    artifacts = _load_raw_artifacts(raw_root)
    decision_splits = _decision_splits(artifacts)
    records = tuple(
        record
        for artifact in artifacts
        if (record := _record_from_artifact(artifact, decision_splits[_decision_id(artifact)]))
        is not None
    )
    for record in records:
        validate_sft_record(record)
    return records


def write_production_sft_dataset(
    *,
    raw_root: Path = DEFAULT_RAW_ROOT,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    plan_path: Path = DEFAULT_PLAN_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> ProductionSFTBuildSummary:
    """Write production SFT records, plan, and summary files."""

    records = build_production_sft_records(raw_root)
    raw_artifact_count = len(_load_raw_artifacts(raw_root))
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    dataset_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps(_training_plan(dataset_path, output_dir), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    dataset_report = validate_sft_dataset(dataset_path)
    summary = ProductionSFTBuildSummary(
        status="production_sft_dataset_ready",
        raw_root=_path_text(raw_root),
        dataset_path=_path_text(dataset_path),
        plan_path=_path_text(plan_path),
        summary_path=_path_text(summary_path),
        raw_artifact_count=raw_artifact_count,
        record_count=dataset_report.record_count,
        split_counts=dataset_report.split_counts,
        artifact_counts=_artifact_counts(records),
        decision_count=len({_decision_id_from_record(record) for record in records}),
    )
    summary_path.write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _load_raw_artifacts(raw_root: Path) -> tuple[Mapping[str, Any], ...]:
    if not raw_root.exists():
        raise FileNotFoundError(f"production raw archive root does not exist: {raw_root}")
    artifacts: list[Mapping[str, Any]] = []
    for path in sorted(raw_root.glob("*/*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            continue
        if payload.get("repository_id") != REPOSITORY_ID:
            continue
        if payload.get("artifact_kind") not in TASK_BY_KIND:
            continue
        artifacts.append(payload)
    if not artifacts:
        raise ValueError(f"no supported production raw artifacts found under {raw_root}")
    return tuple(artifacts)


def _record_from_artifact(artifact: Mapping[str, Any], split: str) -> dict[str, object] | None:
    raw = _raw(artifact)
    artifact_kind = _text(artifact.get("artifact_kind"))
    external_id = _text(artifact.get("external_id"))
    source_url = _source_url(artifact, raw)
    excerpt = _excerpt_for_artifact(artifact_kind, raw)
    if not external_id or not source_url or not excerpt:
        return None

    source_id = f"prod-{external_id}"
    decision_id = _decision_id(artifact)
    task = TASK_BY_KIND[artifact_kind]
    return {
        "schema_version": 1,
        "record_id": f"sft-production-answer-discipline-{external_id}",
        "source_repository": REPOSITORY_ID,
        "split": split,
        "question": _question(artifact_kind),
        "target": {
            "repository_id": REPOSITORY_ID,
            "target_type": artifact_kind,
            "artifact_ids": [external_id],
            "decision_id": decision_id,
        },
        "evidence_pack": {
            "pack_id": f"ep-production-{external_id}",
            "evidence_items": [
                {
                    "source_id": source_id,
                    "artifact_kind": artifact_kind,
                    "source_url": source_url,
                    "excerpt": excerpt,
                }
            ],
        },
        "ideal_answer": {
            "answer": _ideal_answer(artifact_kind, raw),
            "citations": [source_id],
            "unsupported_claims": [],
            "confidence": "medium",
        },
        "labels": {
            "task": task,
            "requires_abstention": artifact_kind in {"issue_comment", "review_comment", "ci_job"},
            "generated_from": "production_raw_archive",
            "decision_id": decision_id,
        },
    }


def _decision_splits(artifacts: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    decision_ids = sorted({_decision_id(artifact) for artifact in artifacts})
    return {decision_id: _split_for_index(index) for index, decision_id in enumerate(decision_ids)}


def _split_for_index(index: int) -> str:
    bucket = index % 10
    if bucket < 8:
        return "train"
    if bucket == 8:
        return "validation"
    return "test"


def _decision_id(artifact: Mapping[str, Any]) -> str:
    raw = _raw(artifact)
    kind = _text(artifact.get("artifact_kind"))
    if kind == "pull_request":
        return f"pr:{_text(raw.get('number'))}"
    if kind in {"review", "review_comment"}:
        pull = _first_match(
            (
                _text(raw.get("pull_request_url")),
                _nested(raw, "_links", "pull_request", "href"),
                _text(raw.get("html_url")),
            ),
            r"/pulls?/(\d+)",
        )
        return f"pr:{pull or _text(artifact.get('external_id'))}"
    if kind == "issue":
        return f"issue:{_text(raw.get('number'))}"
    if kind == "issue_comment":
        issue = _first_match((_text(raw.get("issue_url")), _text(raw.get("html_url"))), r"/issues/(\d+)")
        return f"issue:{issue or _text(artifact.get('external_id'))}"
    if kind == "ci_run":
        return f"ci-run:{_text(raw.get('databaseId'))}"
    if kind == "ci_job":
        run = _first_match((_text(raw.get("url")),), r"/actions/runs/(\d+)")
        return f"ci-run:{run or _text(raw.get('databaseId'))}"
    if kind == "commit":
        return f"commit:{_text(raw.get('sha')) or _text(artifact.get('external_id'))}"
    return f"{kind}:{_text(artifact.get('external_id'))}"


def _decision_id_from_record(record: Mapping[str, object]) -> str:
    target = record["target"]
    if isinstance(target, Mapping) and isinstance(target.get("decision_id"), str):
        return target["decision_id"]
    return str(record["record_id"])


def _source_url(artifact: Mapping[str, Any], raw: Mapping[str, Any]) -> str:
    return (
        _text(artifact.get("source_url"))
        or _text(raw.get("html_url"))
        or _text(raw.get("url"))
    )


def _question(artifact_kind: str) -> str:
    if artifact_kind == "pull_request":
        return "Using only this Evidence Pack, what can be safely stated about the pull request, and what remains unknown?"
    if artifact_kind == "commit":
        return "Using only this Evidence Pack, what implementation rationale is supported, and what should not be inferred?"
    if artifact_kind in {"review", "review_comment"}:
        return "Using only this Evidence Pack, what review judgment or concern is supported, and what should remain unstated?"
    if artifact_kind in {"ci_run", "ci_job"}:
        return "Using only this Evidence Pack, what CI status or risk signal is supported, and what root cause remains unknown?"
    return "Using only this Evidence Pack, what issue or discussion fact is supported, and what should remain unknown?"


def _ideal_answer(artifact_kind: str, raw: Mapping[str, Any]) -> str:
    fact = _supported_fact(artifact_kind, raw)
    unknown = _unknown_boundary(artifact_kind)
    return f"The evidence supports this bounded statement: {fact} {unknown}"


def _supported_fact(artifact_kind: str, raw: Mapping[str, Any]) -> str:
    if artifact_kind == "pull_request":
        return (
            f"the pull request titled {_quoted(raw.get('title'))} is in state "
            f"{_quoted(raw.get('state'))}, with base {_quoted(raw.get('baseRefName'))} "
            f"and head {_quoted(raw.get('headRefName'))}."
        )
    if artifact_kind == "issue":
        return f"the issue titled {_quoted(raw.get('title'))} is in state {_quoted(raw.get('state'))}."
    if artifact_kind == "issue_comment":
        return f"the issue comment says {_quoted(_clean_text(raw.get('body')))}."
    if artifact_kind == "review":
        return f"the pull request review state is {_quoted(raw.get('state'))} and its body says {_quoted(_clean_text(raw.get('body')))}."
    if artifact_kind == "review_comment":
        path = _text(raw.get("path")) or "an unspecified file"
        return f"the review comment on {path} says {_quoted(_clean_text(raw.get('body')))}."
    if artifact_kind == "ci_run":
        return (
            f"the workflow {_quoted(raw.get('workflowName'))} for {_quoted(raw.get('displayTitle'))} "
            f"has status {_quoted(raw.get('status'))} and conclusion {_quoted(raw.get('conclusion'))}."
        )
    if artifact_kind == "ci_job":
        return (
            f"the CI job {_quoted(raw.get('name'))} has status {_quoted(raw.get('status'))} "
            f"and conclusion {_quoted(raw.get('conclusion'))}."
        )
    if artifact_kind == "commit":
        return f"the commit message starts with {_quoted(_commit_title(raw))}."
    return "the artifact contains the cited repository evidence."


def _unknown_boundary(artifact_kind: str) -> str:
    if artifact_kind in {"ci_run", "ci_job"}:
        return "It does not establish an underlying root cause or user impact without additional evidence."
    if artifact_kind in {"review", "review_comment"}:
        return "It does not establish final project consensus or merge outcome unless another cited artifact says so."
    if artifact_kind in {"pull_request", "commit"}:
        return "It does not establish hidden motivation, production impact, or later regressions outside the cited evidence."
    return "It does not establish maintainer intent, reproduction validity, or final resolution beyond the cited evidence."


def _excerpt_for_artifact(artifact_kind: str, raw: Mapping[str, Any]) -> str:
    if artifact_kind == "pull_request":
        parts = [
            f"Pull request title: {_text(raw.get('title'))}",
            f"State: {_text(raw.get('state'))}; base: {_text(raw.get('baseRefName'))}; head: {_text(raw.get('headRefName'))}",
            _clean_text(raw.get("body")),
        ]
    elif artifact_kind == "issue":
        parts = [
            f"Issue title: {_text(raw.get('title'))}",
            f"State: {_text(raw.get('state'))}",
            _clean_text(raw.get("body")),
        ]
    elif artifact_kind == "issue_comment":
        parts = [f"Issue comment: {_clean_text(raw.get('body'))}"]
    elif artifact_kind == "review":
        parts = [
            f"Review state: {_text(raw.get('state'))}",
            f"Review body: {_clean_text(raw.get('body'))}",
        ]
    elif artifact_kind == "review_comment":
        parts = [
            f"Review comment path: {_text(raw.get('path'))}",
            f"Review comment body: {_clean_text(raw.get('body'))}",
            f"Diff context: {_clean_text(raw.get('diff_hunk'))}",
        ]
    elif artifact_kind == "ci_run":
        parts = [
            f"Workflow: {_text(raw.get('workflowName'))}",
            f"Title: {_text(raw.get('displayTitle'))}",
            f"Event: {_text(raw.get('event'))}; status: {_text(raw.get('status'))}; conclusion: {_text(raw.get('conclusion'))}",
            f"Head SHA: {_text(raw.get('headSha'))}",
        ]
    elif artifact_kind == "ci_job":
        parts = [
            f"Job: {_text(raw.get('name'))}",
            f"Status: {_text(raw.get('status'))}; conclusion: {_text(raw.get('conclusion'))}",
            f"Steps: {_steps(raw.get('steps'))}",
        ]
    elif artifact_kind == "commit":
        parts = [
            f"Commit message: {_commit_message(raw)}",
            f"Stats: {_stats(raw.get('stats'))}",
            f"Changed files: {_changed_files(raw.get('files'))}",
        ]
    else:
        parts = [_clean_text(raw)]
    return _clip(" ".join(part for part in parts if part and part.strip()), 1200)


def _training_plan(dataset_path: Path, output_dir: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ready",
        "method": "qlora",
        "base_model": BASE_MODEL,
        "dataset_path": _path_text(dataset_path),
        "output_dir": _path_text(output_dir),
        "seed": 20260726,
        "reason": "Production raw archive artifacts were converted into evidence-pack answer-discipline SFT records.",
        "training_args": {
            "max_seq_length": 4096,
            "num_train_epochs": 1,
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 8,
            "learning_rate": 0.0002,
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "logging_steps": 10,
            "optim": "paged_adamw_8bit",
            "target_modules": [
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
        },
        "safety_checks": [
            "dataset validates with SFT policy",
            "records are generated from Evidence Pack excerpts, not raw closed-book facts",
            "decision IDs are assigned to only one split",
            "closed-book leakage suite must pass before and after adapter training",
        ],
    }


def _artifact_counts(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        target = record["target"]
        if not isinstance(target, Mapping):
            continue
        kind = str(target["target_type"])
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def _raw(artifact: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = artifact.get("raw", {})
    return raw if isinstance(raw, Mapping) else {}


def _nested(raw: Mapping[str, Any], *keys: str) -> str:
    value: Any = raw
    for key in keys:
        if not isinstance(value, Mapping):
            return ""
        value = value.get(key)
    return _text(value)


def _first_match(values: Sequence[str], pattern: str) -> str:
    for value in values:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return ""


def _clean_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return " ".join(f"{key}: {_clean_text(item)}" for key, item in sorted(value.items()))
    if isinstance(value, list | tuple):
        return " ".join(_clean_text(item) for item in value)
    return re.sub(r"\s+", " ", _text(value)).strip()


def _clip(text: str, max_length: int) -> str:
    text = text.strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def _quoted(value: Any) -> str:
    text = _clip(_clean_text(value), 180)
    return json.dumps(text or "unknown", ensure_ascii=False)


def _commit_title(raw: Mapping[str, Any]) -> str:
    return _commit_message(raw).splitlines()[0].strip()


def _commit_message(raw: Mapping[str, Any]) -> str:
    commit = raw.get("commit")
    if isinstance(commit, Mapping):
        return _clean_text(commit.get("message"))
    return ""


def _stats(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    return (
        f"additions={_text(value.get('additions'))}, "
        f"deletions={_text(value.get('deletions'))}, total={_text(value.get('total'))}"
    )


def _changed_files(value: Any) -> str:
    if not isinstance(value, list | tuple):
        return ""
    filenames = []
    for item in value[:8]:
        if isinstance(item, Mapping):
            filenames.append(_text(item.get("filename")))
    return ", ".join(filename for filename in filenames if filename)


def _steps(value: Any) -> str:
    if not isinstance(value, list | tuple):
        return ""
    steps = []
    for item in value[:10]:
        if isinstance(item, Mapping):
            steps.append(
                f"{_text(item.get('number'))}:{_text(item.get('name'))}={_text(item.get('conclusion')) or _text(item.get('status'))}"
            )
    return "; ".join(steps)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _path_text(path: Path) -> str:
    return path.as_posix()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    summary = write_production_sft_dataset(
        raw_root=args.raw_root,
        dataset_path=args.dataset,
        plan_path=args.plan,
        summary_path=args.summary,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
