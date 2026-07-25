"""RAG-only answer and judge interface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol

from git_archaeologist.answer_schema import (
    AnswerClaim,
    AnswerVerdict,
    Confidence,
    StructuredAnswer,
    safe_schema_error,
    validate_answer,
)
from git_archaeologist.evidence_pack import EvidencePack


RAG_SYSTEM_PROMPT_VERSION = "rag-only-answer-v1"
RAG_SYSTEM_PROMPT = (
    "Answer only from the supplied Evidence Pack. "
    "Separate confirmed facts from inferences. "
    "Do not use repository knowledge outside the Evidence Pack. "
    "If the Evidence Pack is missing or insufficient, abstain with missing_information."
)


@dataclass(frozen=True)
class RagModelConfig:
    """Model and prompt settings recorded for reproducible evaluation."""

    model_version: str
    prompt_version: str = RAG_SYSTEM_PROMPT_VERSION
    temperature: float = 0.0

    def validate(self) -> None:
        if not self.model_version:
            raise ValueError("model_version must be non-empty")
        if not self.prompt_version:
            raise ValueError("prompt_version must be non-empty")
        if self.temperature < 0:
            raise ValueError("temperature must be zero or positive")


@dataclass(frozen=True)
class RagPromptPayload:
    """Prompt payload sent to an answer or judge backend."""

    question: str
    system_prompt: str
    evidence_pack: Mapping[str, Any]
    model_config: RagModelConfig

    def to_dict(self) -> dict[str, object]:
        self.model_config.validate()
        return {
            "question": self.question,
            "system_prompt": self.system_prompt,
            "evidence_pack": dict(self.evidence_pack),
            "model_config": asdict(self.model_config),
        }


class RagAnswerBackend(Protocol):
    """Replaceable backend for answer or judge model calls."""

    def generate(self, payload: RagPromptPayload) -> Mapping[str, Any]:
        """Return a raw structured answer mapping."""


@dataclass(frozen=True)
class RagAnswerResult:
    """Validated answer plus reproducibility metadata."""

    answer: StructuredAnswer
    model_version: str
    prompt_version: str
    evidence_pack_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "answer": self.answer.to_dict(),
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "evidence_pack_id": self.evidence_pack_id,
        }


def build_rag_prompt_payload(
    *,
    evidence_pack: EvidencePack,
    model_config: RagModelConfig,
) -> RagPromptPayload:
    """Create a prompt payload that carries only the Evidence Pack."""

    model_config.validate()
    return RagPromptPayload(
        question=evidence_pack.question,
        system_prompt=RAG_SYSTEM_PROMPT,
        evidence_pack=evidence_pack.to_dict(),
        model_config=model_config,
    )


def answer_from_evidence_pack(
    *,
    evidence_pack: EvidencePack,
    model_config: RagModelConfig,
    backend: RagAnswerBackend,
) -> RagAnswerResult:
    """Generate a validated structured answer, abstaining when evidence is absent."""

    if not evidence_pack.items:
        return RagAnswerResult(
            answer=_insufficient_answer("Evidence Pack has no items."),
            model_version=model_config.model_version,
            prompt_version=model_config.prompt_version,
            evidence_pack_id=evidence_pack.pack_id,
        )

    payload = build_rag_prompt_payload(evidence_pack=evidence_pack, model_config=model_config)
    try:
        answer = validate_answer(backend.generate(payload))
    except Exception as error:
        answer = validate_answer(safe_schema_error(error))

    return RagAnswerResult(
        answer=answer,
        model_version=model_config.model_version,
        prompt_version=model_config.prompt_version,
        evidence_pack_id=evidence_pack.pack_id,
    )


def _insufficient_answer(reason: str) -> StructuredAnswer:
    return StructuredAnswer(
        verdict=AnswerVerdict.INSUFFICIENT_EVIDENCE,
        confirmed_reasons=(),
        evidence=(),
        inferences=(),
        potential_risks=(),
        recommended_actions=("Collect or retrieve supporting evidence before answering.",),
        missing_information=(reason,),
        confidence=Confidence.LOW,
    )
