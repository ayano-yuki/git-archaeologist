from __future__ import annotations

import unittest

from git_archaeologist.chat_flow import (
    ChatAnswer,
    ChatCitation,
    ChatEvidenceItem,
    ChatEvidencePack,
    ChatFlowStatus,
    ChatTarget,
    ChatTargetResolution,
    ChatVerificationReport,
    TargetResolutionState,
    run_chat_flow,
)
from git_archaeologist.current_change_context import (
    CurrentChangeFetchError,
    PullRequestLocator,
    PullRequestMetadata,
)
from git_archaeologist.demo_chat import run_demo_chat


class ChatFlowTests(unittest.TestCase):
    def test_pr_file_question_runs_to_verified_answer(self) -> None:
        result = run_chat_flow(
            _pr_file_input(),
            index_version="index-v1",
            target_resolver=_ResolvedTarget(),
            evidence_retriever=_Evidence(),
            answer_generator=_Answer(),
            citation_verifier=_Verifier(),
            current_change_client=_CurrentChangeClient(),
        )

        self.assertEqual(ChatFlowStatus.ANSWERED, result.status)
        self.assertEqual("target-1", result.target.target_id)
        self.assertEqual("head-sha", result.current_change.metadata.head_sha)
        self.assertEqual("source-1", result.answer.citations[0].source_id)
        self.assertTrue(result.verification.is_supported)

    def test_code_snippet_question_runs_through_same_flow(self) -> None:
        result = run_chat_flow(
            "```js\nfunction createRoot() {}\n```\nWhy does this exist?",
            index_version="index-v1",
            target_resolver=_ResolvedTarget(),
            evidence_retriever=_Evidence(),
            answer_generator=_Answer(),
            citation_verifier=_Verifier(),
        )

        self.assertEqual(ChatFlowStatus.ANSWERED, result.status)
        self.assertIsNone(result.current_change)

    def test_pr_without_target_asks_for_clarification(self) -> None:
        result = run_chat_flow(
            "https://github.com/facebook/react/pull/12345\nWhy was this changed?",
            index_version="index-v1",
            target_resolver=_ShouldNotResolve(),
            evidence_retriever=_Evidence(),
            answer_generator=_Answer(),
            citation_verifier=_Verifier(),
        )

        self.assertEqual(ChatFlowStatus.NEEDS_CLARIFICATION, result.status)
        self.assertIn("file path", result.message)

    def test_empty_evidence_abstains_without_generation(self) -> None:
        result = run_chat_flow(
            _pr_file_input(),
            index_version="index-v1",
            target_resolver=_ResolvedTarget(),
            evidence_retriever=_NoEvidence(),
            answer_generator=_ShouldNotAnswer(),
            citation_verifier=_Verifier(),
        )

        self.assertEqual(ChatFlowStatus.INSUFFICIENT_EVIDENCE, result.status)
        self.assertEqual("insufficient_evidence", result.answer.verdict)
        self.assertIn("断言できません", result.answer.text)

    def test_current_change_fetch_failure_is_safe_failure(self) -> None:
        result = run_chat_flow(
            _pr_file_input(),
            index_version="index-v1",
            target_resolver=_ResolvedTarget(),
            evidence_retriever=_Evidence(),
            answer_generator=_Answer(),
            citation_verifier=_Verifier(),
            current_change_client=_FailingCurrentChangeClient(),
        )

        self.assertEqual(ChatFlowStatus.FAILED, result.status)
        self.assertIn("古い情報", result.message)

    def test_citation_failure_blocks_display(self) -> None:
        result = run_chat_flow(
            _pr_file_input(),
            index_version="index-v1",
            target_resolver=_ResolvedTarget(),
            evidence_retriever=_Evidence(),
            answer_generator=_Answer(),
            citation_verifier=_FailingVerifier(),
        )

        self.assertEqual(ChatFlowStatus.FAILED, result.status)
        self.assertIn("引用検証", result.message)

    def test_demo_chat_is_locally_runnable(self) -> None:
        result = run_demo_chat()

        self.assertEqual(ChatFlowStatus.ANSWERED, result.status)
        self.assertEqual("demo-pack-1", result.evidence_pack.pack_id)


def _pr_file_input() -> str:
    return (
        "https://github.com/facebook/react/pull/12345\n"
        "file: packages/react-dom/src/client/ReactDOMRoot.js\n"
        "Question: explain why this implementation changed."
    )


class _ResolvedTarget:
    def resolve(self, interpreted_input):
        target = ChatTarget(
            target_id="target-1",
            target_type="file",
            file_path=interpreted_input.file_path,
            pull_request_id="facebook/react#12345",
        )
        return ChatTargetResolution(TargetResolutionState.RESOLVED, (target,), target, "resolved")


class _ShouldNotResolve:
    def resolve(self, interpreted_input):
        raise AssertionError("resolver should not be called before clarification")


class _Evidence:
    def retrieve(self, request):
        return ChatEvidencePack(
            pack_id="pack-1",
            index_version="index-v1",
            items=(
                ChatEvidenceItem(
                    source_id="source-1",
                    source_url="https://github.com/facebook/react/pull/12345#discussion_r1",
                    text="The review explains the implementation change.",
                    parent_event_id="pr-12345",
                ),
            ),
        )


class _NoEvidence:
    def retrieve(self, request):
        return ChatEvidencePack(pack_id="empty-pack", index_version="index-v1", items=())


class _Answer:
    def generate(self, request):
        item = request.evidence_pack.items[0]
        return ChatAnswer(
            verdict="explained",
            text="The change is explained by the cited review.",
            citations=(ChatCitation(item.source_id, item.source_url, "review explanation"),),
        )


class _ShouldNotAnswer:
    def generate(self, request):
        raise AssertionError("answer generator should not be called")


class _Verifier:
    def verify(self, answer, evidence_pack):
        return ChatVerificationReport(is_supported=True)


class _FailingVerifier:
    def verify(self, answer, evidence_pack):
        return ChatVerificationReport(is_supported=False, failures=("source-1",))


class _CurrentChangeClient:
    def fetch_metadata(self, locator: PullRequestLocator) -> PullRequestMetadata:
        return PullRequestMetadata(
            repository=locator.repository,
            number=locator.number,
            title="Test PR",
            state="OPEN",
            head_sha="head-sha",
            base_sha="base-sha",
            html_url=locator.url,
        )

    def fetch_diff(self, locator: PullRequestLocator) -> str:
        return "@@ -1 +1 @@\n-old\n+new"


class _FailingCurrentChangeClient:
    def fetch_metadata(self, locator: PullRequestLocator) -> PullRequestMetadata:
        raise CurrentChangeFetchError("network unavailable")

    def fetch_diff(self, locator: PullRequestLocator) -> str:
        raise AssertionError("diff should not be fetched after metadata failure")


if __name__ == "__main__":
    unittest.main()
