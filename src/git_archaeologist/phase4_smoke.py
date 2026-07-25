"""Deterministic Phase4 smoke check for line and condition archaeology."""

from __future__ import annotations

import json

from git_archaeologist.rag.lineage_answering import build_lineage_answer
from git_archaeologist.search.lineage_analysis import (
    LineageRelationKind,
    build_condition_history_entry,
    detect_file_lineage,
    detect_symbol_lineage,
    parse_blame_porcelain,
    separate_rationale,
)


def run_phase4_smoke() -> dict[str, object]:
    """Exercise blame parsing, lineage, condition history, and answers."""

    blame = (
        "abc1234 10 20 1\n"
        "author Example\n"
        "\tif (supportsFallback && hasContainer) {\n"
    )
    candidates = parse_blame_porcelain(
        blame,
        file_path="packages/react-dom/client.js",
        requested_start=20,
        requested_end=20,
    )
    file_edge = detect_file_lineage(
        source_path="packages/react-dom/old-client.js",
        target_path="packages/react-dom/client.js",
        source_content="function createRoot() { return supportsFallback && hasContainer; }",
        target_content="function createRoot() { return supportsFallback && hasContainer; }",
    )
    symbol_edge = detect_symbol_lineage(
        source_symbol="legacyCreateRoot",
        target_symbol="ReactDOM.createRoot",
        source_body="return supportsFallback && hasContainer",
        target_body="return supportsFallback && hasContainer",
    )
    condition = build_condition_history_entry(
        commit_sha="abc1234",
        file_path="packages/react-dom/client.js",
        symbol_name="ReactDOM.createRoot",
        before_expression="supportsFallback",
        after_expression="supportsFallback && hasContainer",
        branch_body_excerpt="preserve fallback path",
        related_tests=("ReactDOM.createRoot.test",),
    )
    rationale = separate_rationale(
        introduction_evidence="Review required the fallback guard.",
        maintenance_evidence="A later test keeps the fallback path covered.",
        current_state="maintained",
    )
    answer = build_lineage_answer(
        origin_candidates=candidates,
        rationale=rationale,
        condition_history=(condition,),
    )
    passed = (
        len(candidates) == 1
        and file_edge.relation_kind is LineageRelationKind.MOVED
        and symbol_edge.relation_kind is LineageRelationKind.RENAMED
        and condition.related_tests == ("ReactDOM.createRoot.test",)
        and answer.status.value == "answered"
    )
    return {
        "status": "phase4_smoke_passed" if passed else "phase4_smoke_failed",
        "origin_candidates": [candidate.to_dict() for candidate in candidates],
        "file_lineage": file_edge.to_dict(),
        "symbol_lineage": symbol_edge.to_dict(),
        "condition_history": condition.to_dict(),
        "rationale": rationale.to_dict(),
        "answer": answer.to_dict(),
    }


def main() -> None:
    print(json.dumps(run_phase4_smoke(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
