"""Parser support policy for the react/react MVP corpus."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


PARSER_POLICY_ID = "react-react-parser-policy-v1"
TARGET_REPOSITORY_ID = "react/react"


class ParserBackend(StrEnum):
    """Parser backend selected by the policy."""

    TREE_SITTER = "tree_sitter"
    FILE_LEVEL = "file_level"
    NONE = "none"


class ParserSupport(StrEnum):
    """How much structural information the MVP may extract."""

    SYMBOLS_SUPPORTED = "symbols_supported"
    FILE_LEVEL_ONLY = "file_level_only"
    UNSUPPORTED = "unsupported"


class SymbolExtractionMode(StrEnum):
    """Symbol extraction behavior for a path."""

    AST_SYMBOLS = "ast_symbols"
    FILE_AND_SNIPPET_ONLY = "file_and_snippet_only"
    REJECTED = "rejected"


@dataclass(frozen=True)
class LanguageParserRule:
    language_id: str
    display_name: str
    extensions: tuple[str, ...]
    support: ParserSupport
    backend: ParserBackend
    symbol_extraction: SymbolExtractionMode
    parser_package: str | None
    parser_language: str | None
    notes: str


@dataclass(frozen=True)
class FallbackBehavior:
    reason: str
    allowed_operations: tuple[str, ...]
    disallowed_operations: tuple[str, ...]
    user_visible_outcome: str


@dataclass(frozen=True)
class UnsupportedLanguagePolicy:
    support: ParserSupport
    backend: ParserBackend
    symbol_extraction: SymbolExtractionMode
    behavior: str
    user_visible_outcome: str


@dataclass(frozen=True)
class ParserDecision:
    path: str
    extension: str
    support: ParserSupport
    backend: ParserBackend
    symbol_extraction: SymbolExtractionMode
    language_id: str | None
    parser_package: str | None
    parser_language: str | None
    can_extract_symbols: bool
    fallback_required: bool
    reason: str
    no_llm_guessing: bool


@dataclass(frozen=True)
class ParserPolicy:
    policy_id: str
    repository_id: str
    supported_languages: tuple[LanguageParserRule, ...]
    file_level_languages: tuple[LanguageParserRule, ...]
    fallback_behavior: FallbackBehavior
    unsupported_language_policy: UnsupportedLanguagePolicy
    no_llm_guessing_rule: str

    @property
    def all_rules(self) -> tuple[LanguageParserRule, ...]:
        return self.supported_languages + self.file_level_languages


def load_react_mvp_parser_policy() -> ParserPolicy:
    """Return the static parser policy for the react/react MVP target."""

    return ParserPolicy(
        policy_id=PARSER_POLICY_ID,
        repository_id=TARGET_REPOSITORY_ID,
        supported_languages=(
            LanguageParserRule(
                language_id="typescript",
                display_name="TypeScript",
                extensions=(".ts",),
                support=ParserSupport.SYMBOLS_SUPPORTED,
                backend=ParserBackend.TREE_SITTER,
                symbol_extraction=SymbolExtractionMode.AST_SYMBOLS,
                parser_package="tree-sitter-typescript",
                parser_language="typescript",
                notes="Use TypeScript AST nodes for functions, classes, methods, exports, and type-level declarations when useful for symbol lookup.",
            ),
            LanguageParserRule(
                language_id="tsx",
                display_name="TSX",
                extensions=(".tsx",),
                support=ParserSupport.SYMBOLS_SUPPORTED,
                backend=ParserBackend.TREE_SITTER,
                symbol_extraction=SymbolExtractionMode.AST_SYMBOLS,
                parser_package="tree-sitter-typescript",
                parser_language="tsx",
                notes="Use the TSX grammar so JSX elements embedded in TypeScript files do not break symbol ranges.",
            ),
            LanguageParserRule(
                language_id="javascript",
                display_name="JavaScript",
                extensions=(".js", ".mjs", ".cjs"),
                support=ParserSupport.SYMBOLS_SUPPORTED,
                backend=ParserBackend.TREE_SITTER,
                symbol_extraction=SymbolExtractionMode.AST_SYMBOLS,
                parser_package="tree-sitter-javascript",
                parser_language="javascript",
                notes="React's JavaScript sources may contain Flow-style annotations; parser failures fall back to file/snippet matching instead of guessed symbols.",
            ),
            LanguageParserRule(
                language_id="jsx",
                display_name="JSX",
                extensions=(".jsx",),
                support=ParserSupport.SYMBOLS_SUPPORTED,
                backend=ParserBackend.TREE_SITTER,
                symbol_extraction=SymbolExtractionMode.AST_SYMBOLS,
                parser_package="tree-sitter-javascript",
                parser_language="javascript",
                notes="Use JavaScript grammar with JSX support for component and hook symbol ranges.",
            ),
        ),
        file_level_languages=(
            LanguageParserRule(
                language_id="json",
                display_name="JSON",
                extensions=(".json", ".json5"),
                support=ParserSupport.FILE_LEVEL_ONLY,
                backend=ParserBackend.FILE_LEVEL,
                symbol_extraction=SymbolExtractionMode.FILE_AND_SNIPPET_ONLY,
                parser_package=None,
                parser_language=None,
                notes="Configuration files are kept searchable at file and snippet level; they do not produce function or class symbols.",
            ),
            LanguageParserRule(
                language_id="markdown",
                display_name="Markdown",
                extensions=(".md", ".mdx"),
                support=ParserSupport.FILE_LEVEL_ONLY,
                backend=ParserBackend.FILE_LEVEL,
                symbol_extraction=SymbolExtractionMode.FILE_AND_SNIPPET_ONLY,
                parser_package=None,
                parser_language=None,
                notes="Documentation files can provide evidence, but they are not part of the MVP Symbol Index.",
            ),
            LanguageParserRule(
                language_id="yaml",
                display_name="YAML",
                extensions=(".yaml", ".yml"),
                support=ParserSupport.FILE_LEVEL_ONLY,
                backend=ParserBackend.FILE_LEVEL,
                symbol_extraction=SymbolExtractionMode.FILE_AND_SNIPPET_ONLY,
                parser_package=None,
                parser_language=None,
                notes="Workflow and config files are indexed only by path, snippet, and diff hunk.",
            ),
        ),
        fallback_behavior=FallbackBehavior(
            reason="The selected parser is unavailable or cannot parse the file confidently.",
            allowed_operations=(
                "repository_relative_path_match",
                "exact_code_snippet_match",
                "normalized_code_snippet_match",
                "diff_hunk_match",
                "git_log_S_or_G_search",
                "return_candidates_for_user_clarification",
            ),
            disallowed_operations=(
                "llm_guess_symbol_boundary",
                "llm_choose_one_candidate_without_evidence",
                "regex_only_function_boundary_indexing",
                "brace_counting_as_symbol_index",
            ),
            user_visible_outcome=(
                "Degrade to file, hunk, or snippet-level candidates and mark symbol extraction as unavailable."
            ),
        ),
        unsupported_language_policy=UnsupportedLanguagePolicy(
            support=ParserSupport.UNSUPPORTED,
            backend=ParserBackend.NONE,
            symbol_extraction=SymbolExtractionMode.REJECTED,
            behavior=(
                "Do not extract symbols. Keep the file as unsupported for MVP Symbol Index purposes and ask for a supported source file, exact snippet, or line/hunk context when needed."
            ),
            user_visible_outcome="Report that the language is outside the MVP parser policy instead of guessing.",
        ),
        no_llm_guessing_rule=(
            "LLMs must not infer parser support, symbol boundaries, or the single best target candidate. "
            "They may only explain candidates produced by deterministic parsing or matching."
        ),
    )


def classify_path(
    path: str,
    *,
    parser_available: bool = True,
    policy: ParserPolicy | None = None,
) -> ParserDecision:
    """Classify a repository path according to the parser policy."""

    parser_policy = policy or load_react_mvp_parser_policy()
    extension = _path_extension(path)
    rule = _find_rule(extension, parser_policy.all_rules)

    if rule is None:
        unsupported = parser_policy.unsupported_language_policy
        return ParserDecision(
            path=path,
            extension=extension,
            support=unsupported.support,
            backend=unsupported.backend,
            symbol_extraction=unsupported.symbol_extraction,
            language_id=None,
            parser_package=None,
            parser_language=None,
            can_extract_symbols=False,
            fallback_required=False,
            reason=unsupported.behavior,
            no_llm_guessing=True,
        )

    if rule.support == ParserSupport.SYMBOLS_SUPPORTED and not parser_available:
        return ParserDecision(
            path=path,
            extension=extension,
            support=ParserSupport.FILE_LEVEL_ONLY,
            backend=ParserBackend.FILE_LEVEL,
            symbol_extraction=SymbolExtractionMode.FILE_AND_SNIPPET_ONLY,
            language_id=rule.language_id,
            parser_package=rule.parser_package,
            parser_language=rule.parser_language,
            can_extract_symbols=False,
            fallback_required=True,
            reason=parser_policy.fallback_behavior.reason,
            no_llm_guessing=True,
        )

    return ParserDecision(
        path=path,
        extension=extension,
        support=rule.support,
        backend=rule.backend,
        symbol_extraction=rule.symbol_extraction,
        language_id=rule.language_id,
        parser_package=rule.parser_package,
        parser_language=rule.parser_language,
        can_extract_symbols=rule.symbol_extraction == SymbolExtractionMode.AST_SYMBOLS,
        fallback_required=False,
        reason=rule.notes,
        no_llm_guessing=True,
    )


def parser_policy_to_dict(policy: ParserPolicy | None = None) -> dict[str, Any]:
    """Return the parser policy as a plain dictionary for docs or reports."""

    return asdict(policy or load_react_mvp_parser_policy())


def supported_source_extensions(policy: ParserPolicy | None = None) -> tuple[str, ...]:
    """Return extensions that are intended to produce AST-backed symbols."""

    parser_policy = policy or load_react_mvp_parser_policy()
    extensions: list[str] = []
    for rule in parser_policy.supported_languages:
        extensions.extend(rule.extensions)
    return tuple(extensions)


def _find_rule(
    extension: str, rules: tuple[LanguageParserRule, ...]
) -> LanguageParserRule | None:
    for rule in rules:
        if extension in rule.extensions:
            return rule
    return None


def _path_extension(path: str) -> str:
    normalized = path.replace("\\", "/")
    if "/" in normalized:
        return PurePosixPath(normalized).suffix.lower()
    return PureWindowsPath(path).suffix.lower()
