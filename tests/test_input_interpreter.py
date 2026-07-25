from __future__ import annotations

import unittest

from git_archaeologist.input_interpreter import QueryIntent, interpret_input
from git_archaeologist.mvp_contracts import InputDecision, MvpInputKind


class InputInterpreterTests(unittest.TestCase):
    def test_interprets_pr_url_with_file_as_rationale_request(self) -> None:
        interpreted = interpret_input(
            "https://github.com/facebook/react/pull/12345\n"
            "file: packages/react-dom/src/client/ReactDOMRoot.js\n"
            "Why was this implementation changed?"
        )

        self.assertEqual(InputDecision.TARGET_RESOLVED, interpreted.decision)
        self.assertEqual(QueryIntent.IMPLEMENTATION_RATIONALE, interpreted.intent)
        self.assertEqual(MvpInputKind.PR_URL_WITH_TARGET, interpreted.kind)
        self.assertEqual("facebook/react", interpreted.repository)
        self.assertEqual(12345, interpreted.pull_request_number)
        self.assertTrue(interpreted.can_resolve_target)

    def test_interprets_pr_url_with_symbol_as_change_risk(self) -> None:
        interpreted = interpret_input(
            "https://github.com/facebook/react/pull/12345\n"
            "function: createRoot\n"
            "Could this conflict with historical compatibility constraints?"
        )

        self.assertEqual(QueryIntent.CHANGE_RISK, interpreted.intent)
        self.assertEqual("createRoot", interpreted.symbol_name)

    def test_interprets_code_snippet_with_question(self) -> None:
        interpreted = interpret_input(
            "```js\n"
            "const root = createRoot(container);\n"
            "root.render(<App />);\n"
            "```\n"
            "What risk would changing this create?"
        )

        self.assertEqual(InputDecision.TARGET_RESOLVED, interpreted.decision)
        self.assertEqual(MvpInputKind.CODE_SNIPPET_WITH_QUESTION, interpreted.kind)
        self.assertEqual(QueryIntent.CHANGE_RISK, interpreted.intent)
        self.assertIn("createRoot", interpreted.code_snippet or "")

    def test_distinguishes_target_unknown_from_unsupported(self) -> None:
        ambiguous = interpret_input(
            "https://github.com/facebook/react/pull/12345\nWhy was this changed?"
        )
        unsupported = interpret_input("Why did React change this behavior?")

        self.assertEqual(InputDecision.NEEDS_CLARIFICATION, ambiguous.decision)
        self.assertEqual(QueryIntent.TARGET_UNKNOWN, ambiguous.intent)
        self.assertEqual(InputDecision.UNSUPPORTED, unsupported.decision)
        self.assertEqual(QueryIntent.UNSUPPORTED, unsupported.intent)

    def test_to_dict_uses_serializable_values(self) -> None:
        interpreted = interpret_input(
            "https://github.com/facebook/react/pull/12345\n"
            "file: packages/react/src/ReactHooks.js\n"
            "なぜこの実装になった？"
        )

        payload = interpreted.to_dict()

        self.assertEqual("target_resolved", payload["decision"])
        self.assertEqual("implementation_rationale", payload["intent"])
        self.assertEqual("pr_url_with_file_or_symbol", payload["kind"])


if __name__ == "__main__":
    unittest.main()
