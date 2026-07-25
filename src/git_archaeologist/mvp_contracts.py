"""MVP input and quality contracts for Git Archaeologist.

The definitions in this module are intentionally static. Evaluation runs should
record this contract version before execution and must not change targets after
looking at results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import re
from typing import Any


CONTRACT_VERSION = "mvp-input-quality-v1"
EVALUATION_CORPUS = "react/react-derived-history"
FREEZE_POLICY = (
    "Freeze the contract version, dataset version, and evaluator version before "
    "an evaluation run. Do not loosen or rewrite targets after seeing results; "
    "any target change requires a new contract version and a reason recorded "
    "before the next run."
)


class MvpInputKind(StrEnum):
    """Accepted MVP input families."""

    PR_URL_WITH_TARGET = "pr_url_with_file_or_symbol"
    CODE_SNIPPET_WITH_QUESTION = "code_snippet_with_natural_language_question"


class ExampleCategory(StrEnum):
    """Example classification categories used by the evaluation contract."""

    VALID = "valid"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class InputDecision(StrEnum):
    """Deterministic routing outcomes for MVP inputs."""

    TARGET_RESOLVED = "target_resolved"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    required: bool
    description: str


@dataclass(frozen=True)
class InputFormatSpec:
    kind: MvpInputKind
    description: str
    fields: tuple[FieldSpec, ...]
    target_resolution: str
    unsupported_scope: str


@dataclass(frozen=True)
class InputExample:
    example_id: str
    category: ExampleCategory
    raw_input: str
    expected_decision: InputDecision
    expected_kind: MvpInputKind | None
    note: str


@dataclass(frozen=True)
class StructuredMvpInput:
    decision: InputDecision
    kind: MvpInputKind | None
    pr_url: str | None = None
    repository: str | None = None
    pull_request_number: int | None = None
    file_path: str | None = None
    symbol_name: str | None = None
    code_snippet: str | None = None
    question: str | None = None
    clarification_reason: str | None = None


@dataclass(frozen=True)
class QualityMetricTarget:
    metric_id: str
    name: str
    definition: str
    provisional_target: str
    measurement: str
    failure_owner: str


@dataclass(frozen=True)
class MvpContract:
    version: str
    evaluation_corpus: str
    accepted_input_formats: tuple[InputFormatSpec, ...]
    examples: tuple[InputExample, ...]
    quality_targets: tuple[QualityMetricTarget, ...]
    freeze_policy: str


_PR_URL_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/pull/(?P<number>\d+)"
)
_FIELD_RE = re.compile(
    r"^\s*(?P<label>file|path|function|symbol|ファイル|関数|シンボル)\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_FENCED_CODE_RE = re.compile(r"```(?:[A-Za-z0-9_+.-]+)?\s*\n(?P<code>.*?)```", re.DOTALL)


def load_mvp_contract() -> MvpContract:
    """Return the complete static contract for MVP evaluation."""

    return MvpContract(
        version=CONTRACT_VERSION,
        evaluation_corpus=EVALUATION_CORPUS,
        accepted_input_formats=load_mvp_input_formats(),
        examples=load_mvp_input_examples(),
        quality_targets=load_mvp_quality_targets(),
        freeze_policy=FREEZE_POLICY,
    )


def load_mvp_input_formats() -> tuple[InputFormatSpec, ...]:
    """Return the two input forms accepted by the MVP."""

    return (
        InputFormatSpec(
            kind=MvpInputKind.PR_URL_WITH_TARGET,
            description="A GitHub pull request URL plus either a repository file path or a function/symbol name.",
            fields=(
                FieldSpec("pr_url", True, "GitHub pull request URL in https://github.com/<owner>/<repo>/pull/<number> form."),
                FieldSpec("file_path", False, "Repository-relative file path. Required when symbol_name is absent."),
                FieldSpec("symbol_name", False, "Function, class, hook, or exported symbol name. Required when file_path is absent."),
                FieldSpec("question", False, "Optional natural language focus such as rationale or change risk."),
            ),
            target_resolution=(
                "Resolve the PR first, then resolve the file path or symbol deterministically. "
                "If the path or symbol has multiple candidates, ask for clarification before answer generation."
            ),
            unsupported_scope="Issue URLs, commit URLs without a PR, and PR-only inputs without a file or symbol are outside the MVP target.",
        ),
        InputFormatSpec(
            kind=MvpInputKind.CODE_SNIPPET_WITH_QUESTION,
            description="A fenced code snippet plus a natural language question about rationale or change risk.",
            fields=(
                FieldSpec("code_snippet", True, "Fenced source code copied from the target repository."),
                FieldSpec("question", True, "Natural language question that states the explanation or risk being requested."),
                FieldSpec("repository_context", False, "Optional file path, symbol, or PR hint used only to narrow deterministic search."),
            ),
            target_resolution=(
                "Search exact code first, then normalized code, lexical similarity, and symbol candidates. "
                "Multiple matches must be returned as candidates instead of being guessed by an LLM."
            ),
            unsupported_scope="Screenshots, prose-only questions, and snippets without a question are outside the answer-generation path.",
        ),
    )


def load_mvp_input_examples() -> tuple[InputExample, ...]:
    """Return valid, ambiguous, and invalid examples for the accepted input forms."""

    return (
        InputExample(
            example_id="valid-pr-file",
            category=ExampleCategory.VALID,
            raw_input=(
                "https://github.com/facebook/react/pull/12345\n"
                "file: packages/react-dom/src/client/ReactDOMRoot.js\n"
                "Question: explain why this implementation changed."
            ),
            expected_decision=InputDecision.TARGET_RESOLVED,
            expected_kind=MvpInputKind.PR_URL_WITH_TARGET,
            note="PR URL plus repository-relative file path.",
        ),
        InputExample(
            example_id="valid-pr-symbol",
            category=ExampleCategory.VALID,
            raw_input=(
                "https://github.com/facebook/react/pull/12345\n"
                "function: createRoot\n"
                "Question: does this change conflict with historical compatibility constraints?"
            ),
            expected_decision=InputDecision.TARGET_RESOLVED,
            expected_kind=MvpInputKind.PR_URL_WITH_TARGET,
            note="PR URL plus function name.",
        ),
        InputExample(
            example_id="valid-code-question",
            category=ExampleCategory.VALID,
            raw_input=(
                "```js\n"
                "function warnIfUpdatesNotWrappedWithActDEV(fiber) {\n"
                "  if (__DEV__) {\n"
                "    // warning body omitted\n"
                "  }\n"
                "}\n"
                "```\n"
                "Why does this warning still exist, and what risk would removing it create?"
            ),
            expected_decision=InputDecision.TARGET_RESOLVED,
            expected_kind=MvpInputKind.CODE_SNIPPET_WITH_QUESTION,
            note="Fenced code plus a natural language question.",
        ),
        InputExample(
            example_id="ambiguous-pr-only",
            category=ExampleCategory.AMBIGUOUS,
            raw_input="https://github.com/facebook/react/pull/12345\nWhy was this changed?",
            expected_decision=InputDecision.NEEDS_CLARIFICATION,
            expected_kind=MvpInputKind.PR_URL_WITH_TARGET,
            note="The PR is known, but the target file or symbol is missing.",
        ),
        InputExample(
            example_id="ambiguous-code-only",
            category=ExampleCategory.AMBIGUOUS,
            raw_input=(
                "```js\n"
                "const root = createRoot(container);\n"
                "root.render(<App />);\n"
                "```"
            ),
            expected_decision=InputDecision.NEEDS_CLARIFICATION,
            expected_kind=MvpInputKind.CODE_SNIPPET_WITH_QUESTION,
            note="The code is present, but the user's question is missing.",
        ),
        InputExample(
            example_id="invalid-prose-only",
            category=ExampleCategory.INVALID,
            raw_input="Why did React change this behavior?",
            expected_decision=InputDecision.UNSUPPORTED,
            expected_kind=None,
            note="No PR URL, file, symbol, or code snippet is available for target resolution.",
        ),
        InputExample(
            example_id="invalid-issue-url",
            category=ExampleCategory.INVALID,
            raw_input="https://github.com/facebook/react/issues/12345\nfile: packages/react/src/ReactHooks.js",
            expected_decision=InputDecision.UNSUPPORTED,
            expected_kind=None,
            note="Issue URLs are not accepted as the primary MVP input.",
        ),
    )


def load_mvp_quality_targets() -> tuple[QualityMetricTarget, ...]:
    """Return provisional quality targets fixed before MVP evaluation."""

    return (
        QualityMetricTarget(
            metric_id="target_resolution_accuracy",
            name="Target resolution accuracy",
            definition="Share of evaluable inputs whose repository, PR, file, symbol, or snippet target is resolved to the annotated target.",
            provisional_target=">= 0.85 on the frozen MVP evaluation set",
            measurement="Evaluate valid inputs separately from ambiguous and invalid routing cases.",
            failure_owner="Input Interpreter / Target Resolver",
        ),
        QualityMetricTarget(
            metric_id="evidence_search_recall_at_5",
            name="Evidence search recall@5",
            definition="Share of questions where at least one required evidence item appears in the top five retrieved evidence candidates.",
            provisional_target=">= 0.80",
            measurement="Use human-labeled required evidence from react/react-derived history.",
            failure_owner="Query Planner / Hybrid Search / Evidence Reranker",
        ),
        QualityMetricTarget(
            metric_id="citation_consistency_rate",
            name="Citation consistency rate",
            definition="Share of cited answer claims whose citation exists and directly supports the claim within the Evidence Pack.",
            provisional_target=">= 0.95",
            measurement="Check each cited claim with deterministic citation validation before model-assisted entailment checks.",
            failure_owner="Answer / Judge LLM / Citation Verifier",
        ),
        QualityMetricTarget(
            metric_id="unsupported_claim_rate",
            name="Unsupported claim rate",
            definition="Share of material answer claims that are not supported by any provided evidence.",
            provisional_target="<= 0.05",
            measurement="Count only material rationale, risk, or factual claims; exclude explicit uncertainty and missing-information statements.",
            failure_owner="Answer / Judge LLM",
        ),
        QualityMetricTarget(
            metric_id="risk_warning_precision",
            name="Risk warning precision",
            definition="Share of emitted risk warnings that match an annotated compatibility, regression, revert, or review-risk label.",
            provisional_target=">= 0.75",
            measurement="Measure warnings only when the answer labels a concrete change risk, not when it asks for more evidence.",
            failure_owner="Risk Judge / Evidence selection",
        ),
        QualityMetricTarget(
            metric_id="answer_latency_p95_seconds",
            name="Answer latency p95",
            definition="95th percentile wall-clock time from structured input to validated answer on an already indexed local repository.",
            provisional_target="<= 30 seconds",
            measurement="Exclude first-time collection and indexing; include target resolution, search, rerank, generation, and citation verification.",
            failure_owner="End-to-end runtime",
        ),
    )


def structure_mvp_input(raw_input: str) -> StructuredMvpInput:
    """Best-effort deterministic structure for the MVP input examples.

    This is not the full future Input Interpreter. It encodes the contract-level
    routing decisions needed by evaluation fixtures.
    """

    text = raw_input.strip()
    if not text:
        return StructuredMvpInput(
            decision=InputDecision.UNSUPPORTED,
            kind=None,
            clarification_reason="Input is empty.",
        )

    pr_match = _PR_URL_RE.search(text)
    if pr_match:
        file_path, symbol_name = _extract_target_fields(text)
        repository = f"{pr_match.group('owner')}/{pr_match.group('repo')}"
        if file_path or symbol_name:
            return StructuredMvpInput(
                decision=InputDecision.TARGET_RESOLVED,
                kind=MvpInputKind.PR_URL_WITH_TARGET,
                pr_url=pr_match.group(0),
                repository=repository,
                pull_request_number=int(pr_match.group("number")),
                file_path=file_path,
                symbol_name=symbol_name,
                question=_extract_question_without_code(text),
            )
        return StructuredMvpInput(
            decision=InputDecision.NEEDS_CLARIFICATION,
            kind=MvpInputKind.PR_URL_WITH_TARGET,
            pr_url=pr_match.group(0),
            repository=repository,
            pull_request_number=int(pr_match.group("number")),
            question=_extract_question_without_code(text),
            clarification_reason="A PR URL must include a repository file path or a symbol/function name.",
        )

    code_match = _FENCED_CODE_RE.search(text)
    if code_match:
        question = _extract_question_without_code(text)
        if question:
            return StructuredMvpInput(
                decision=InputDecision.TARGET_RESOLVED,
                kind=MvpInputKind.CODE_SNIPPET_WITH_QUESTION,
                code_snippet=code_match.group("code").strip(),
                question=question,
            )
        return StructuredMvpInput(
            decision=InputDecision.NEEDS_CLARIFICATION,
            kind=MvpInputKind.CODE_SNIPPET_WITH_QUESTION,
            code_snippet=code_match.group("code").strip(),
            clarification_reason="A code snippet must include a natural language question.",
        )

    return StructuredMvpInput(
        decision=InputDecision.UNSUPPORTED,
        kind=None,
        clarification_reason="Input does not match an MVP PR target or code-snippet question.",
    )


def contract_to_dict(contract: MvpContract | None = None) -> dict[str, Any]:
    """Return the contract as a plain dictionary for reporting or serialization."""

    return asdict(contract or load_mvp_contract())


def _extract_target_fields(text: str) -> tuple[str | None, str | None]:
    file_path: str | None = None
    symbol_name: str | None = None

    for match in _FIELD_RE.finditer(text):
        label = match.group("label").lower()
        value = match.group("value").strip()
        if label in {"file", "path", "ファイル"} and _is_probable_file_path(value):
            file_path = value
        elif label in {"function", "symbol", "関数", "シンボル"} and value:
            symbol_name = value

    return file_path, symbol_name


def _is_probable_file_path(value: str) -> bool:
    return "/" in value or "\\" in value or "." in value


def _extract_question_without_code(text: str) -> str | None:
    without_code = _FENCED_CODE_RE.sub(" ", text)
    without_url = _PR_URL_RE.sub(" ", without_code)
    without_fields = _FIELD_RE.sub(" ", without_url)
    question = " ".join(without_fields.split())
    return question or None
