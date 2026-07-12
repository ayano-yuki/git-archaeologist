from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from llm_tuning_lab.data.bundles import read_jsonl, write_jsonl
from llm_tuning_lab.config import load_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Git Archaeologist evaluation predictions.")
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--adapter-path", type=Path)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument(
        "--copy-expected",
        action="store_true",
        help="Offline test mode: copy benchmark expected answers into prediction records.",
    )
    args = parser.parse_args()

    if args.copy_expected:
        count = write_jsonl(args.output, _copy_expected_predictions(read_jsonl(args.benchmark)))
        print(f"predictions: {count} -> {args.output}")
        return 0

    if args.model_config is None:
        parser.error("--model-config is required unless --copy-expected is set")
    count = write_jsonl(
        args.output,
        _model_predictions(
            read_jsonl(args.benchmark),
            model_config=load_yaml(args.model_config),
            adapter_path=args.adapter_path,
            max_new_tokens=args.max_new_tokens,
        ),
    )
    print(f"predictions: {count} -> {args.output}")
    return 0


def _copy_expected_predictions(records: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for index, record in enumerate(records, start=1):
        if "id" not in record:
            raise ValueError(f"benchmark record {index} is missing required field 'id'")
        expected = record.get("expected")
        if not isinstance(expected, dict):
            raise ValueError(f"benchmark record {record['id']} is missing object field 'expected'")
        yield {"id": str(record["id"]), "prediction": expected}


def _model_predictions(
    records: Iterable[dict[str, Any]],
    *,
    model_config: dict[str, Any],
    adapter_path: Path | None,
    max_new_tokens: int,
) -> Iterable[dict[str, Any]]:
    deps = _load_generation_dependencies()
    tokenizer = deps["AutoTokenizer"].from_pretrained(
        model_config["model_name_or_path"],
        trust_remote_code=model_config.get("trust_remote_code", False),
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs = {"trust_remote_code": model_config.get("trust_remote_code", False)}
    if model_config.get("device_map"):
        model_kwargs["device_map"] = model_config["device_map"]
    if adapter_path:
        model = deps["AutoPeftModelForCausalLM"].from_pretrained(str(adapter_path), **model_kwargs)
    else:
        model = deps["AutoModelForCausalLM"].from_pretrained(
            model_config["model_name_or_path"],
            **model_kwargs,
        )
    model.eval()

    for record in records:
        prompt = _benchmark_prompt(record)
        inputs = tokenizer(prompt, return_tensors="pt")
        if hasattr(model, "device"):
            inputs = {key: value.to(model.device) for key, value in inputs.items()}
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
        generated = tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True)
        yield {"id": str(record["id"]), "prediction": _parse_prediction(generated)}


def _benchmark_prompt(record: dict[str, Any]) -> str:
    bundle = record.get("bundle") if isinstance(record.get("bundle"), dict) else {}
    evidence_lines = []
    for item in bundle.get("evidence", []) if isinstance(bundle.get("evidence"), list) else []:
        if isinstance(item, dict):
            evidence_lines.append(
                f"[{item.get('evidence_id')}] {item.get('kind')} {item.get('source_id')}: {item.get('summary')}"
            )
    return (
        "You are Git Archaeologist. Return only JSON matching schema_version "
        "git-archaeologist.answer.v1.\n"
        f"Repository: {bundle.get('repo', '')}\n"
        f"Thread: {bundle.get('thread_key', '')}\n"
        f"Question: {record.get('question', '')}\n\n"
        "Evidence:\n"
        + "\n".join(evidence_lines)
    )


def _parse_prediction(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {"answer": stripped}
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(stripped[start : end + 1])
                return parsed if isinstance(parsed, dict) else {"answer": stripped}
            except json.JSONDecodeError:
                pass
    return {"answer": stripped}


def _load_generation_dependencies() -> dict[str, Any]:
    try:
        from peft import AutoPeftModelForCausalLM
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Generation dependencies are missing. Install them with: "
            "uv sync --system-certs --extra train --group dev"
        ) from exc
    return {
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoPeftModelForCausalLM": AutoPeftModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
    }


if __name__ == "__main__":
    raise SystemExit(main())
