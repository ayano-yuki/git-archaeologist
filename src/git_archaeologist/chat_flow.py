"""End-to-end MVP chat orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol

from git_archaeologist.current_change_context import (
    CurrentChangeClient,
    CurrentChangeContext,
    CurrentChangeStatus,
    build_current_change_context,
)
from git_archaeologist.input_interpreter import InterpretedInput, interpret_input


class ChatFlowStatus(StrEnum):
    """Top-level chat flow outcome."""

    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    FAILED = "failed"


class TargetResolutionState(StrEnum):
    """Target resolver outcome consumed by chat flow."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ChatTarget:
    """Resolved repository target."""

    target_id: str
    target_type: str
    file_path: str | None = None
    symbol_name: str | None = None
    pull_request_id: str | None = None

    def validate(self) -> None:
        if not self.target_id:
            raise ValueError("target_id must be non-empty")
        if not self.target_type:
            raise ValueError("target_type must be non-empty")


@dataclass(frozen=True)
class ChatTargetResolution:
    """Result returned by a target resolver backend."""

    state: TargetResolutionState
    candidates: tuple[ChatTarget, ...]
    selected: ChatTarget | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if self.selected is not None:
            self.selected.validate()


@dataclass(frozen=True)
class ChatEvidenceItem:
    """Citation-ready evidence shown to the user."""

    source_id: str
    source_url: str
    text: str
    parent_event_id: str

    def validate(self) -> None:
        for field_name in ("source_id", "source_url", "text", "parent_event_id"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be non-empty")
        if not self.source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be an http or https URL")


@dataclass(frozen=True)
class ChatEvidencePack:
    """Evidence Pack view used by the chat layer."""

    pack_id: str
    items: tuple[ChatEvidenceItem, ...]
    index_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        if not self.pack_id:
            raise ValueError("pack_id must be non-empty")
        if not self.index_version:
            raise ValueError("index_version must be non-empty")
        for item in self.items:
            item.validate()


@dataclass(frozen=True)
class ChatCitation:
    """Citation displayed with the generated answer."""

    source_id: str
    source_url: str
    supports: str


@dataclass(frozen=True)
class ChatAnswer:
    """Structured answer shown to the user."""

    verdict: str
    text: str
    citations: tuple[ChatCitation, ...] = ()
    missing_information: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "citations", tuple(self.citations))
        object.__setattr__(self, "missing_information", tuple(self.missing_information))


@dataclass(frozen=True)
class ChatVerificationReport:
    """Citation verification result."""

    is_supported: bool
    failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "failures", tuple(self.failures))


@dataclass(frozen=True)
class ChatRetrievalRequest:
    """Inputs passed to evidence retrieval."""

    interpreted_input: InterpretedInput
    target: ChatTarget
    current_change: CurrentChangeContext | None


@dataclass(frozen=True)
class ChatAnswerRequest:
    """Inputs passed to answer generation."""

    interpreted_input: InterpretedInput
    target: ChatTarget
    evidence_pack: ChatEvidencePack
    current_change: CurrentChangeContext | None


@dataclass(frozen=True)
class ChatFlowResult:
    """End-to-end chat result with safe display payload."""

    status: ChatFlowStatus
    interpreted_input: InterpretedInput
    answer: ChatAnswer | None = None
    target: ChatTarget | None = None
    evidence_pack: ChatEvidencePack | None = None
    current_change: CurrentChangeContext | None = None
    verification: ChatVerificationReport | None = None
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = {
            "status": self.status.value,
            "interpreted_input": self.interpreted_input.to_dict(),
            "answer": asdict(self.answer) if self.answer else None,
            "target": asdict(self.target) if self.target else None,
            "evidence_pack": _evidence_pack_to_dict(self.evidence_pack),
            "current_change": self.current_change.to_dict() if self.current_change else None,
            "verification": asdict(self.verification) if self.verification else None,
            "message": self.message,
        }
        return {key: value for key, value in payload.items() if value is not None}


class TargetResolverBackend(Protocol):
    """Resolve interpreted input to a concrete repository target."""

    def resolve(self, interpreted_input: InterpretedInput) -> ChatTargetResolution:
        """Return target candidates and resolution state."""


class EvidenceRetrieverBackend(Protocol):
    """Retrieve an Evidence Pack for the selected target."""

    def retrieve(self, request: ChatRetrievalRequest) -> ChatEvidencePack:
        """Return citation-ready evidence for answer generation."""


class AnswerGeneratorBackend(Protocol):
    """Generate a structured answer from evidence."""

    def generate(self, request: ChatAnswerRequest) -> ChatAnswer:
        """Return an answer that cites the supplied evidence."""


class CitationVerifierBackend(Protocol):
    """Verify generated citations before display."""

    def verify(self, answer: ChatAnswer, evidence_pack: ChatEvidencePack) -> ChatVerificationReport:
        """Return whether answer citations are supported by the Evidence Pack."""


def run_chat_flow(
    raw_input: str,
    *,
    index_version: str,
    target_resolver: TargetResolverBackend,
    evidence_retriever: EvidenceRetrieverBackend,
    answer_generator: AnswerGeneratorBackend,
    citation_verifier: CitationVerifierBackend,
    current_change_client: CurrentChangeClient | None = None,
) -> ChatFlowResult:
    """Run input interpretation, target resolution, retrieval, answer, and verification."""

    interpreted = interpret_input(raw_input)
    if not interpreted.can_resolve_target:
        return ChatFlowResult(
            status=ChatFlowStatus.NEEDS_CLARIFICATION,
            interpreted_input=interpreted,
            message=interpreted.clarification_reason or "Target clarification is required before answering.",
        )

    current_change = _build_current_change(
        interpreted,
        current_change_client=current_change_client,
        index_version=index_version,
    )
    if current_change is not None and current_change.status is CurrentChangeStatus.FETCH_FAILED:
        return ChatFlowResult(
            status=ChatFlowStatus.FAILED,
            interpreted_input=interpreted,
            current_change=current_change,
            message="最新PR情報を取得できなかったため、古い情報で変更リスクを断言しません。",
        )

    target_resolution = target_resolver.resolve(interpreted)
    if target_resolution.state is TargetResolutionState.AMBIGUOUS:
        return ChatFlowResult(
            status=ChatFlowStatus.NEEDS_CLARIFICATION,
            interpreted_input=interpreted,
            current_change=current_change,
            message=target_resolution.reason or "Multiple target candidates remain.",
        )
    if target_resolution.state is TargetResolutionState.UNRESOLVED or target_resolution.selected is None:
        return ChatFlowResult(
            status=ChatFlowStatus.FAILED,
            interpreted_input=interpreted,
            current_change=current_change,
            message=target_resolution.reason or "Target could not be resolved.",
        )

    target = target_resolution.selected
    evidence_pack = evidence_retriever.retrieve(
        ChatRetrievalRequest(
            interpreted_input=interpreted,
            target=target,
            current_change=current_change,
        )
    )
    if not evidence_pack.items:
        return ChatFlowResult(
            status=ChatFlowStatus.INSUFFICIENT_EVIDENCE,
            interpreted_input=interpreted,
            target=target,
            evidence_pack=evidence_pack,
            current_change=current_change,
            answer=ChatAnswer(
                verdict="insufficient_evidence",
                text="Evidence Packに根拠がないため、この質問には断言できません。",
                missing_information=("supporting Evidence Pack items",),
            ),
            message="Evidence Pack is empty; answer generation was skipped.",
        )

    answer = answer_generator.generate(
        ChatAnswerRequest(
            interpreted_input=interpreted,
            target=target,
            evidence_pack=evidence_pack,
            current_change=current_change,
        )
    )
    verification = citation_verifier.verify(answer, evidence_pack)
    if not verification.is_supported:
        return ChatFlowResult(
            status=ChatFlowStatus.FAILED,
            interpreted_input=interpreted,
            target=target,
            evidence_pack=evidence_pack,
            current_change=current_change,
            answer=answer,
            verification=verification,
            message="引用検証に失敗したため、回答を安全に表示できません。",
        )

    return ChatFlowResult(
        status=ChatFlowStatus.ANSWERED,
        interpreted_input=interpreted,
        target=target,
        evidence_pack=evidence_pack,
        current_change=current_change,
        answer=answer,
        verification=verification,
        message="Answer generated and citations verified.",
    )


def _build_current_change(
    interpreted: InterpretedInput,
    *,
    current_change_client: CurrentChangeClient | None,
    index_version: str,
) -> CurrentChangeContext | None:
    if current_change_client is None or interpreted.pr_url is None:
        return None
    return build_current_change_context(
        interpreted.pr_url,
        client=current_change_client,
        index_version=index_version,
    )


def _evidence_pack_to_dict(evidence_pack: ChatEvidencePack | None) -> dict[str, object] | None:
    if evidence_pack is None:
        return None
    return {
        "pack_id": evidence_pack.pack_id,
        "index_version": evidence_pack.index_version,
        "items": [asdict(item) for item in evidence_pack.items],
    }
