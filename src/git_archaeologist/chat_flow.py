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
from git_archaeologist.query_trace import QueryTrace, QueryTraceStore, start_query_trace


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
    trace_id: str | None = None
    answer: ChatAnswer | None = None
    target: ChatTarget | None = None
    evidence_pack: ChatEvidencePack | None = None
    current_change: CurrentChangeContext | None = None
    verification: ChatVerificationReport | None = None
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = {
            "status": self.status.value,
            "trace_id": self.trace_id,
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
    trace_store: QueryTraceStore | None = None,
    model_version: str = "unknown-model",
    query_id: str | None = None,
) -> ChatFlowResult:
    """Run input interpretation, target resolution, retrieval, answer, and verification."""

    trace = start_query_trace(
        raw_input,
        index_version=index_version,
        model_version=model_version,
        query_id=query_id,
    )
    interpreted = interpret_input(raw_input)
    trace = trace.add_step(
        "input_interpretation",
        "ok",
        {
            "kind": interpreted.kind.value if interpreted.kind else None,
            "can_resolve_target": interpreted.can_resolve_target,
            "repository": interpreted.repository,
            "pull_request_number": interpreted.pull_request_number,
            "file_path": interpreted.file_path,
            "symbol_name": interpreted.symbol_name,
        },
    )
    if not interpreted.can_resolve_target:
        return _finish_with_trace(
            ChatFlowResult(
                status=ChatFlowStatus.NEEDS_CLARIFICATION,
                interpreted_input=interpreted,
                trace_id=trace.query_id,
                message=interpreted.clarification_reason or "Target clarification is required before answering.",
            ),
            trace=trace,
            trace_store=trace_store,
        )

    current_change = _build_current_change(
        interpreted,
        current_change_client=current_change_client,
        index_version=index_version,
    )
    trace = trace.add_step(
        "current_change_context",
        "ok" if current_change is None else current_change.status.value,
        {"status": current_change.status.value if current_change else "not_requested"},
    )
    if current_change is not None and current_change.status is CurrentChangeStatus.FETCH_FAILED:
        return _finish_with_trace(
            ChatFlowResult(
                status=ChatFlowStatus.FAILED,
                interpreted_input=interpreted,
                trace_id=trace.query_id,
                current_change=current_change,
                message="最新PR情報を取得できなかったため、古い情報で変更リスクを断言しません。",
            ),
            trace=trace,
            trace_store=trace_store,
        )

    target_resolution = target_resolver.resolve(interpreted)
    trace = trace.add_step(
        "target_resolution",
        target_resolution.state.value,
        {
            "candidate_ids": [candidate.target_id for candidate in target_resolution.candidates],
            "selected_id": target_resolution.selected.target_id if target_resolution.selected else None,
            "reason": target_resolution.reason,
        },
    )
    if target_resolution.state is TargetResolutionState.AMBIGUOUS:
        return _finish_with_trace(
            ChatFlowResult(
                status=ChatFlowStatus.NEEDS_CLARIFICATION,
                interpreted_input=interpreted,
                trace_id=trace.query_id,
                current_change=current_change,
                message=target_resolution.reason or "Multiple target candidates remain.",
            ),
            trace=trace,
            trace_store=trace_store,
        )
    if target_resolution.state is TargetResolutionState.UNRESOLVED or target_resolution.selected is None:
        return _finish_with_trace(
            ChatFlowResult(
                status=ChatFlowStatus.FAILED,
                interpreted_input=interpreted,
                trace_id=trace.query_id,
                current_change=current_change,
                message=target_resolution.reason or "Target could not be resolved.",
            ),
            trace=trace,
            trace_store=trace_store,
        )

    target = target_resolution.selected
    evidence_pack = evidence_retriever.retrieve(
        ChatRetrievalRequest(
            interpreted_input=interpreted,
            target=target,
            current_change=current_change,
        )
    )
    trace = trace.add_step(
        "evidence_retrieval",
        "ok",
        {
            "search_query": interpreted.question,
            "graph_expansion": "current_change" if current_change else "indexed_history",
            "pack_id": evidence_pack.pack_id,
            "index_version": evidence_pack.index_version,
            "rerank_order": [item.source_id for item in evidence_pack.items],
        },
    )
    if not evidence_pack.items:
        return _finish_with_trace(
            ChatFlowResult(
                status=ChatFlowStatus.INSUFFICIENT_EVIDENCE,
                interpreted_input=interpreted,
                trace_id=trace.query_id,
                target=target,
                evidence_pack=evidence_pack,
                current_change=current_change,
                answer=ChatAnswer(
                    verdict="insufficient_evidence",
                    text="Evidence Packに根拠がないため、この質問には断言できません。",
                    missing_information=("supporting Evidence Pack items",),
                ),
                message="Evidence Pack is empty; answer generation was skipped.",
            ),
            trace=trace,
            trace_store=trace_store,
        )

    answer = answer_generator.generate(
        ChatAnswerRequest(
            interpreted_input=interpreted,
            target=target,
            evidence_pack=evidence_pack,
            current_change=current_change,
        )
    )
    trace = trace.add_step(
        "answer_generation",
        "ok",
        {"model_version": model_version, "verdict": answer.verdict, "citation_ids": [citation.source_id for citation in answer.citations]},
    )
    verification = citation_verifier.verify(answer, evidence_pack)
    trace = trace.add_step(
        "citation_verification",
        "ok" if verification.is_supported else "failed",
        {"is_supported": verification.is_supported, "failures": list(verification.failures)},
    )
    if not verification.is_supported:
        return _finish_with_trace(
            ChatFlowResult(
                status=ChatFlowStatus.FAILED,
                interpreted_input=interpreted,
                trace_id=trace.query_id,
                target=target,
                evidence_pack=evidence_pack,
                current_change=current_change,
                answer=answer,
                verification=verification,
                message="引用検証に失敗したため、回答を安全に表示できません。",
            ),
            trace=trace,
            trace_store=trace_store,
        )

    return _finish_with_trace(
        ChatFlowResult(
            status=ChatFlowStatus.ANSWERED,
            interpreted_input=interpreted,
            trace_id=trace.query_id,
            target=target,
            evidence_pack=evidence_pack,
            current_change=current_change,
            answer=answer,
            verification=verification,
            message="Answer generated and citations verified.",
        ),
        trace=trace,
        trace_store=trace_store,
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


def _finish_with_trace(
    result: ChatFlowResult,
    *,
    trace: QueryTrace,
    trace_store: QueryTraceStore | None,
) -> ChatFlowResult:
    completed = trace.complete(result.status.value)
    if trace_store is not None:
        trace_store.save(completed)
    return result
