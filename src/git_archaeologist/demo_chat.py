"""Runnable local MVP chat demo."""

from __future__ import annotations

import json

from git_archaeologist.chat_flow import (
    ChatAnswer,
    ChatCitation,
    ChatEvidenceItem,
    ChatEvidencePack,
    ChatFlowResult,
    ChatTarget,
    ChatTargetResolution,
    ChatVerificationReport,
    TargetResolutionState,
    run_chat_flow,
)
from git_archaeologist.input_interpreter import InterpretedInput


DEMO_INPUT = (
    "https://github.com/facebook/react/pull/12345\n"
    "file: packages/react-dom/src/client/ReactDOMRoot.js\n"
    "Question: explain why this implementation changed."
)


def run_demo_chat(raw_input: str = DEMO_INPUT) -> ChatFlowResult:
    """Run the smoke-test demo without external services."""

    return run_chat_flow(
        raw_input,
        index_version="demo-index-v1",
        target_resolver=_DemoTargetResolver(),
        evidence_retriever=_DemoEvidenceRetriever(),
        answer_generator=_DemoAnswerGenerator(),
        citation_verifier=_DemoCitationVerifier(),
    )


class _DemoTargetResolver:
    def resolve(self, interpreted_input: InterpretedInput) -> ChatTargetResolution:
        target_id = interpreted_input.file_path or interpreted_input.symbol_name or "snippet-target"
        return ChatTargetResolution(
            state=TargetResolutionState.RESOLVED,
            candidates=(
                ChatTarget(
                    target_id=target_id,
                    target_type=interpreted_input.kind.value if interpreted_input.kind else "unknown",
                    file_path=interpreted_input.file_path,
                    symbol_name=interpreted_input.symbol_name,
                    pull_request_id=(
                        f"{interpreted_input.repository}#{interpreted_input.pull_request_number}"
                        if interpreted_input.repository and interpreted_input.pull_request_number
                        else None
                    ),
                ),
            ),
            selected=ChatTarget(
                target_id=target_id,
                target_type=interpreted_input.kind.value if interpreted_input.kind else "unknown",
                file_path=interpreted_input.file_path,
                symbol_name=interpreted_input.symbol_name,
                pull_request_id=(
                    f"{interpreted_input.repository}#{interpreted_input.pull_request_number}"
                    if interpreted_input.repository and interpreted_input.pull_request_number
                    else None
                ),
            ),
            reason="demo target resolved from interpreted input",
        )


class _DemoEvidenceRetriever:
    def retrieve(self, request) -> ChatEvidencePack:
        return ChatEvidencePack(
            pack_id="demo-pack-1",
            index_version="demo-index-v1",
            items=(
                ChatEvidenceItem(
                    source_id="demo-review-1",
                    source_url="https://github.com/facebook/react/pull/12345#discussion_r1",
                    parent_event_id="demo-pr-12345",
                    text="The review asked for this implementation shape to keep the change explainable.",
                ),
            ),
        )


class _DemoAnswerGenerator:
    def generate(self, request) -> ChatAnswer:
        item = request.evidence_pack.items[0]
        return ChatAnswer(
            verdict="explained",
            text="The cited review is the only provided evidence, so the demo answer limits itself to that rationale.",
            citations=(ChatCitation(item.source_id, item.source_url, "review rationale"),),
        )


class _DemoCitationVerifier:
    def verify(self, answer: ChatAnswer, evidence_pack: ChatEvidencePack) -> ChatVerificationReport:
        sources = {item.source_id: item.source_url for item in evidence_pack.items}
        failures = tuple(
            citation.source_id
            for citation in answer.citations
            if sources.get(citation.source_id) != citation.source_url
        )
        return ChatVerificationReport(is_supported=not failures, failures=failures)


def main() -> None:
    print(json.dumps(run_demo_chat().to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
