"""Run answer-quality checks against a trained answer-discipline adapter."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from git_archaeologist.evaluation.sft_data_policy import SFTRecord
from git_archaeologist.evaluation.sft_dataset import load_sft_jsonl
from git_archaeologist.evaluation.sft_training_plan import load_sft_training_plan
from git_archaeologist.evaluation.train_sft import DEFAULT_PLAN_PATH


MODEL_NAME = "Qwen--Qwen2.5-Coder-7B-Instruct"
DEFAULT_ADAPTER_DIR = Path(f"data/{MODEL_NAME}/models/answer-discipline-qlora")
DEFAULT_OUTPUT_PATH = Path(
    f"data/{MODEL_NAME}/eval/answer-quality/answer-discipline-production-quality-report.json"
)
VALID_CONFIDENCE_VALUES = frozenset({"low", "medium", "high"})


@dataclass(frozen=True)
class AnswerQualityThresholds:
    """Minimum rates for the adapter smoke-quality gate."""

    parse_success_rate: float = 0.90
    citation_precision_rate: float = 0.90
    expected_citation_recall_rate: float = 0.80
    unsupported_claims_empty_rate: float = 0.95
    non_empty_answer_rate: float = 0.95

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class AnswerQualityCaseResult:
    """Per-record quality checks for one generated SFT answer."""

    record_id: str
    split: str
    target_type: str
    generated_text: str
    parsed_answer: dict[str, object] | None
    expected_citations: tuple[str, ...]
    predicted_citations: tuple[str, ...]
    parse_success: bool
    citation_precision_passed: bool
    expected_citation_recall_passed: bool
    unsupported_claims_empty: bool
    non_empty_answer: bool
    confidence_valid: bool
    passed: bool
    failure_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["expected_citations"] = list(self.expected_citations)
        payload["predicted_citations"] = list(self.predicted_citations)
        payload["failure_reasons"] = list(self.failure_reasons)
        return payload


@dataclass(frozen=True)
class AnswerQualityReport:
    """Serializable answer-quality report for a trained adapter."""

    status: str
    plan_path: str
    adapter_dir: str
    dataset_path: str
    split: str
    case_count: int
    metrics: dict[str, float]
    thresholds: AnswerQualityThresholds
    cases: tuple[AnswerQualityCaseResult, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "plan_path": self.plan_path,
            "adapter_dir": self.adapter_dir,
            "dataset_path": self.dataset_path,
            "split": self.split,
            "case_count": self.case_count,
            "metrics": self.metrics,
            "thresholds": self.thresholds.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
            "notes": list(self.notes),
        }


def build_sft_inference_prompt(record: SFTRecord) -> str:
    """Render the inference prompt matching the SFT training prefix."""

    evidence_lines = []
    for item in record.evidence_pack["evidence_items"]:
        evidence_lines.append(
            "\n".join(
                (
                    f"- source_id: {item['source_id']}",
                    f"  kind: {item['artifact_kind']}",
                    f"  url: {item['source_url']}",
                    f"  excerpt: {item['excerpt']}",
                )
            )
        )
    return "\n".join(
        (
            "### System",
            (
                "Answer only from the Evidence Pack. Separate supported facts, "
                "inference, and unknowns. Cite source IDs for every supported claim."
            ),
            "### Repository",
            record.source_repository,
            "### Task",
            str(record.labels.get("task", "answer_discipline")),
            "### Target",
            json.dumps(dict(record.target), ensure_ascii=False, sort_keys=True),
            "### Question",
            record.question,
            "### Evidence Pack",
            "\n".join(evidence_lines),
            "### Ideal Answer",
            "",
        )
    )


def evaluate_generated_answer(
    record: SFTRecord,
    generated_text: str,
) -> AnswerQualityCaseResult:
    """Score one generated answer against answer-discipline contracts."""

    parsed = parse_generated_answer(generated_text)
    expected_citations = tuple(str(item) for item in record.ideal_answer["citations"])
    evidence_source_ids = {
        str(item["source_id"]) for item in record.evidence_pack["evidence_items"]
    }
    predicted_citations = _string_tuple(parsed.get("citations")) if parsed else ()
    unsupported_claims = parsed.get("unsupported_claims") if parsed else None
    answer = parsed.get("answer") if parsed else None
    confidence = parsed.get("confidence") if parsed else None

    parse_success = parsed is not None
    citation_precision_passed = bool(predicted_citations) and set(predicted_citations) <= evidence_source_ids
    expected_citation_recall_passed = set(expected_citations) <= set(predicted_citations)
    unsupported_claims_empty = unsupported_claims == []
    non_empty_answer = isinstance(answer, str) and bool(answer.strip())
    confidence_valid = isinstance(confidence, str) and confidence in VALID_CONFIDENCE_VALUES

    failures: list[str] = []
    if not parse_success:
        failures.append("generated text did not contain a JSON object")
    if not citation_precision_passed:
        failures.append("citations were empty or referenced unknown source IDs")
    if not expected_citation_recall_passed:
        failures.append("expected citation source IDs were not all cited")
    if not unsupported_claims_empty:
        failures.append("unsupported_claims was not an empty list")
    if not non_empty_answer:
        failures.append("answer was empty or missing")
    if not confidence_valid:
        failures.append("confidence was missing or invalid")

    return AnswerQualityCaseResult(
        record_id=record.record_id,
        split=record.split.value,
        target_type=str(record.target["target_type"]),
        generated_text=generated_text,
        parsed_answer=parsed,
        expected_citations=expected_citations,
        predicted_citations=predicted_citations,
        parse_success=parse_success,
        citation_precision_passed=citation_precision_passed,
        expected_citation_recall_passed=expected_citation_recall_passed,
        unsupported_claims_empty=unsupported_claims_empty,
        non_empty_answer=non_empty_answer,
        confidence_valid=confidence_valid,
        passed=not failures,
        failure_reasons=tuple(failures),
    )


def parse_generated_answer(generated_text: str) -> dict[str, object] | None:
    """Extract the first JSON object from model output."""

    decoder = json.JSONDecoder()
    stripped = generated_text.strip()
    candidate_starts = [index for index, char in enumerate(stripped) if char == "{"]
    for start in candidate_starts:
        try:
            parsed, _ = decoder.raw_decode(stripped[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return None


def build_answer_quality_report(
    *,
    plan_path: Path,
    adapter_dir: Path,
    dataset_path: Path,
    split: str,
    results: Sequence[AnswerQualityCaseResult],
    thresholds: AnswerQualityThresholds = AnswerQualityThresholds(),
) -> AnswerQualityReport:
    """Aggregate per-case answer-quality checks."""

    metrics = _metrics(results)
    passed = bool(results) and all(
        (
            metrics["parse_success_rate"] >= thresholds.parse_success_rate,
            metrics["citation_precision_rate"] >= thresholds.citation_precision_rate,
            metrics["expected_citation_recall_rate"] >= thresholds.expected_citation_recall_rate,
            metrics["unsupported_claims_empty_rate"] >= thresholds.unsupported_claims_empty_rate,
            metrics["non_empty_answer_rate"] >= thresholds.non_empty_answer_rate,
        )
    )
    return AnswerQualityReport(
        status="answer_quality_passed" if passed else "answer_quality_failed",
        plan_path=plan_path.as_posix(),
        adapter_dir=adapter_dir.as_posix(),
        dataset_path=dataset_path.as_posix(),
        split=split,
        case_count=len(results),
        metrics=metrics,
        thresholds=thresholds,
        cases=tuple(results),
        notes=(
            "This report uses held-out SFT records and checks answer-discipline contracts.",
            "It is a smoke-quality gate, not a substitute for human review of generated rationale quality.",
        ),
    )


def run_answer_quality_evaluation(
    *,
    plan_path: Path,
    adapter_dir: Path,
    split: str,
    limit: int,
    max_new_tokens: int,
    output_path: Path | None,
    load_in_4bit: bool = True,
) -> AnswerQualityReport:
    """Load the trained adapter, generate answers, and write an optional report."""

    plan = load_sft_training_plan(plan_path)
    dataset_path = _resolve_path(plan.dataset_path)
    records = _select_records(load_sft_jsonl(dataset_path), split=split, limit=limit)
    if not records:
        raise ValueError(f"no SFT records selected for split={split!r}")

    backend = _TransformersAdapterBackend(
        base_model=plan.base_model,
        adapter_dir=_resolve_path(str(adapter_dir)),
        load_in_4bit=load_in_4bit,
    )
    results = tuple(
        evaluate_generated_answer(record, backend.generate(build_sft_inference_prompt(record), max_new_tokens=max_new_tokens))
        for record in records
    )
    report = build_answer_quality_report(
        plan_path=plan_path,
        adapter_dir=adapter_dir,
        dataset_path=dataset_path,
        split=split,
        results=results,
    )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


class _TransformersAdapterBackend:
    def __init__(self, *, base_model: str, adapter_dir: Path, load_in_4bit: bool) -> None:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        tokenizer_source = adapter_dir if (adapter_dir / "tokenizer.json").exists() else base_model
        self._tokenizer = AutoTokenizer.from_pretrained(tokenizer_source, trust_remote_code=True)
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        kwargs: dict[str, object] = {"device_map": "auto", "trust_remote_code": True}
        if load_in_4bit:
            compute_dtype = (
                torch.bfloat16
                if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
                else torch.float16
            )
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=compute_dtype,
                bnb_4bit_use_double_quant=True,
            )
        model = AutoModelForCausalLM.from_pretrained(base_model, **kwargs)
        self._model = PeftModel.from_pretrained(model, adapter_dir)
        self._model.eval()

    def generate(self, prompt: str, *, max_new_tokens: int) -> str:
        import torch

        inputs = self._tokenizer(prompt, return_tensors="pt")
        model_device = next(self._model.parameters()).device
        inputs = {key: value.to(model_device) for key, value in inputs.items()}
        with torch.inference_mode():
            generated = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        new_tokens = generated[0][inputs["input_ids"].shape[-1] :]
        return self._tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def _select_records(
    records: Sequence[SFTRecord],
    *,
    split: str,
    limit: int,
) -> tuple[SFTRecord, ...]:
    if split == "all":
        selected = tuple(records)
    else:
        selected = tuple(record for record in records if record.split.value == split)
    return selected[:limit] if limit > 0 else selected


def _metrics(results: Sequence[AnswerQualityCaseResult]) -> dict[str, float]:
    if not results:
        return {
            "parse_success_rate": 0.0,
            "citation_precision_rate": 0.0,
            "expected_citation_recall_rate": 0.0,
            "unsupported_claims_empty_rate": 0.0,
            "non_empty_answer_rate": 0.0,
            "pass_rate": 0.0,
        }
    total = len(results)
    return {
        "parse_success_rate": _rate((result.parse_success for result in results), total),
        "citation_precision_rate": _rate((result.citation_precision_passed for result in results), total),
        "expected_citation_recall_rate": _rate((result.expected_citation_recall_passed for result in results), total),
        "unsupported_claims_empty_rate": _rate((result.unsupported_claims_empty for result in results), total),
        "non_empty_answer_rate": _rate((result.non_empty_answer for result in results), total),
        "pass_rate": _rate((result.passed for result in results), total),
    }


def _rate(values: Iterable[bool], total: int) -> float:
    return sum(1 for value in values if value) / total


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--adapter-dir", type=Path, default=DEFAULT_ADAPTER_DIR)
    parser.add_argument("--split", choices=("validation", "test", "train", "all"), default="validation")
    parser.add_argument("--limit", type=int, default=20, help="Number of records to evaluate; 0 means all selected records.")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--no-4bit", action="store_true", help="Load the base model without 4-bit quantization.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = run_answer_quality_evaluation(
        plan_path=args.plan,
        adapter_dir=args.adapter_dir,
        split=args.split,
        limit=args.limit,
        max_new_tokens=args.max_new_tokens,
        output_path=args.output,
        load_in_4bit=not args.no_4bit,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.status == "answer_quality_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
