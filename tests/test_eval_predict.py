import json
import sys
from pathlib import Path

import llm_tuning_lab.eval.predict as predict_module
from llm_tuning_lab.eval.predict import main


def test_predict_copy_expected_writes_prediction_jsonl(tmp_path: Path, monkeypatch) -> None:
    benchmark = tmp_path / "benchmark.jsonl"
    output = tmp_path / "predictions.jsonl"
    expected = {"answer": "Answer.", "facts": [{"text": "Fact", "citations": ["e1"]}]}
    benchmark.write_text(
        json.dumps({"id": "case-1", "expected": expected}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "predict",
            "--benchmark",
            str(benchmark),
            "--output",
            str(output),
            "--copy-expected",
        ],
    )

    assert main() == 0
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert records == [{"id": "case-1", "prediction": expected}]


def test_predict_real_generation_uses_model_dependencies(tmp_path: Path, monkeypatch) -> None:
    benchmark = tmp_path / "benchmark.jsonl"
    output = tmp_path / "predictions.jsonl"
    model_config = tmp_path / "model.yaml"
    model_config.write_text("model_name_or_path: fake/model\ntrust_remote_code: false\n", encoding="utf-8")
    benchmark.write_text(
        json.dumps(
            {
                "id": "case-1",
                "question": "Why?",
                "bundle": {"repo": "acme/project", "thread_key": "pull:1", "evidence": []},
                "expected": {"answer": "Answer."},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(predict_module, "_load_generation_dependencies", _fake_deps)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "predict",
            "--model-config",
            str(model_config),
            "--benchmark",
            str(benchmark),
            "--output",
            str(output),
        ],
    )

    assert main() == 0
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert records == [{"id": "case-1", "prediction": {"answer": "Generated."}}]


def test_eval_model_script_targets_current_run_eval_arguments() -> None:
    script = Path("scripts/eval_model.ps1").read_text(encoding="utf-8")

    assert "llm_tuning_lab.eval.run_eval" in script
    assert "--benchmark" in script
    assert "--predictions" in script
    assert "--prompts" not in script


class FakeTensor:
    def __init__(self, length: int) -> None:
        self.shape = (1, length)

    def to(self, device: str) -> "FakeTensor":
        return self

    def __getitem__(self, key):
        return [1, 2]


class FakeTokenizer:
    pad_token = None
    eos_token = "<eos>"
    eos_token_id = 0

    def __call__(self, text: str, return_tensors: str):
        return {"input_ids": FakeTensor(3)}

    def decode(self, tokens, skip_special_tokens: bool) -> str:
        return '{"answer":"Generated."}'


class FakeModel:
    device = "cpu"

    def eval(self) -> None:
        return None

    def generate(self, **kwargs):
        return [FakeTensor(5)]


class FakeAutoTokenizer:
    @staticmethod
    def from_pretrained(*args, **kwargs) -> FakeTokenizer:
        return FakeTokenizer()


class FakeAutoModelForCausalLM:
    @staticmethod
    def from_pretrained(*args, **kwargs) -> FakeModel:
        return FakeModel()


class FakeAutoPeftModelForCausalLM:
    @staticmethod
    def from_pretrained(*args, **kwargs) -> FakeModel:
        return FakeModel()


def _fake_deps():
    return {
        "AutoModelForCausalLM": FakeAutoModelForCausalLM,
        "AutoPeftModelForCausalLM": FakeAutoPeftModelForCausalLM,
        "AutoTokenizer": FakeAutoTokenizer,
    }
