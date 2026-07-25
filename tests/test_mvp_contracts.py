from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from git_archaeologist import (  # noqa: E402
    CONTRACT_VERSION,
    EVALUATION_CORPUS,
    ExampleCategory,
    InputDecision,
    MvpInputKind,
    contract_to_dict,
    load_mvp_contract,
    load_mvp_input_examples,
    load_mvp_input_formats,
    load_mvp_quality_targets,
    structure_mvp_input,
)


class MvpContractTests(unittest.TestCase):
    def test_accepts_the_two_mvp_input_formats(self) -> None:
        formats = {spec.kind: spec for spec in load_mvp_input_formats()}

        self.assertEqual(
            {
                MvpInputKind.PR_URL_WITH_TARGET,
                MvpInputKind.CODE_SNIPPET_WITH_QUESTION,
            },
            set(formats),
        )
        self.assertIn("file path", formats[MvpInputKind.PR_URL_WITH_TARGET].description)
        self.assertIn("function", formats[MvpInputKind.PR_URL_WITH_TARGET].description)
        self.assertIn("question", formats[MvpInputKind.CODE_SNIPPET_WITH_QUESTION].description)

    def test_examples_cover_valid_ambiguous_and_invalid_inputs(self) -> None:
        examples = load_mvp_input_examples()
        categories = {example.category for example in examples}

        self.assertEqual(
            {
                ExampleCategory.VALID,
                ExampleCategory.AMBIGUOUS,
                ExampleCategory.INVALID,
            },
            categories,
        )

    def test_input_examples_are_structured_to_expected_decisions(self) -> None:
        for example in load_mvp_input_examples():
            with self.subTest(example_id=example.example_id):
                structured = structure_mvp_input(example.raw_input)

                self.assertEqual(example.expected_decision, structured.decision)
                self.assertEqual(example.expected_kind, structured.kind)

        valid_pr = structure_mvp_input(load_mvp_input_examples()[0].raw_input)
        self.assertEqual("facebook/react", valid_pr.repository)
        self.assertEqual(12345, valid_pr.pull_request_number)
        self.assertEqual(
            "packages/react-dom/src/client/ReactDOMRoot.js",
            valid_pr.file_path,
        )

        valid_code = structure_mvp_input(load_mvp_input_examples()[2].raw_input)
        self.assertIn("warnIfUpdatesNotWrappedWithActDEV", valid_code.code_snippet or "")
        self.assertIn("risk", valid_code.question or "")

    def test_quality_metric_targets_are_loaded(self) -> None:
        targets = {target.metric_id: target for target in load_mvp_quality_targets()}

        self.assertEqual(
            {
                "target_resolution_accuracy",
                "evidence_search_recall_at_5",
                "citation_consistency_rate",
                "unsupported_claim_rate",
                "risk_warning_precision",
                "answer_latency_p95_seconds",
            },
            set(targets),
        )
        self.assertIn(">= 0.85", targets["target_resolution_accuracy"].provisional_target)
        self.assertIn(">= 0.80", targets["evidence_search_recall_at_5"].provisional_target)
        self.assertIn(">= 0.95", targets["citation_consistency_rate"].provisional_target)
        self.assertIn("<= 0.05", targets["unsupported_claim_rate"].provisional_target)
        self.assertIn(">= 0.75", targets["risk_warning_precision"].provisional_target)
        self.assertIn("<= 30 seconds", targets["answer_latency_p95_seconds"].provisional_target)

    def test_contract_declares_react_corpus_and_freeze_policy(self) -> None:
        contract = load_mvp_contract()

        self.assertEqual(CONTRACT_VERSION, contract.version)
        self.assertEqual(EVALUATION_CORPUS, contract.evaluation_corpus)
        self.assertIn("react/react", contract.evaluation_corpus)
        self.assertIn("Do not loosen or rewrite targets after seeing results", contract.freeze_policy)

    def test_contract_is_json_serializable(self) -> None:
        payload = contract_to_dict()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertIn(CONTRACT_VERSION, serialized)
        self.assertIn("quality_targets", payload)


if __name__ == "__main__":
    unittest.main()
