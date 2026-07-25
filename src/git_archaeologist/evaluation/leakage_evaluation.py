"""Closed-book leakage evaluation for answer-discipline datasets."""

from __future__ import annotations

from dataclasses import dataclass

from git_archaeologist.evaluation.sft_data_policy import EvaluationCase, ExpectedVerdict


@dataclass(frozen=True)
class ClosedBookPrediction:
    """Model output for one closed-book leakage case."""

    case_id: str
    verdict: str
    answer: str
    cited_source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "cited_source_ids", tuple(self.cited_source_ids))


@dataclass(frozen=True)
class LeakageFinding:
    """One closed-book leakage failure."""

    case_id: str
    reason: str


@dataclass(frozen=True)
class LeakageEvaluationReport:
    """Closed-book leakage evaluation summary."""

    evaluated_case_count: int
    finding_count: int
    findings: tuple[LeakageFinding, ...]

    @property
    def passed(self) -> bool:
        return self.finding_count == 0


def evaluate_closed_book_leakage(
    cases: tuple[EvaluationCase, ...],
    predictions: tuple[ClosedBookPrediction, ...],
) -> LeakageEvaluationReport:
    """Verify that empty-evidence cases abstain instead of leaking facts."""

    prediction_by_case = {prediction.case_id: prediction for prediction in predictions}
    findings: list[LeakageFinding] = []
    evaluated = 0
    for case in cases:
        if not case.is_closed_book_leakage_test:
            continue
        evaluated += 1
        prediction = prediction_by_case.get(case.case_id)
        if prediction is None:
            findings.append(LeakageFinding(case.case_id, "missing prediction"))
            continue
        if prediction.verdict != ExpectedVerdict.UNKNOWN.value:
            findings.append(LeakageFinding(case.case_id, "closed-book case did not abstain"))
        if prediction.cited_source_ids:
            findings.append(LeakageFinding(case.case_id, "closed-book case cited absent evidence"))
        for marker in _forbidden_markers(case):
            if marker.lower() in prediction.answer.lower():
                findings.append(LeakageFinding(case.case_id, f"answer contains forbidden marker: {marker}"))
    return LeakageEvaluationReport(
        evaluated_case_count=evaluated,
        finding_count=len(findings),
        findings=tuple(findings),
    )


def _forbidden_markers(case: EvaluationCase) -> tuple[str, ...]:
    markers = case.expected_behavior.get("forbidden_claim_markers", ())
    if not isinstance(markers, list | tuple) or not all(isinstance(marker, str) for marker in markers):
        raise ValueError("expected_behavior.forbidden_claim_markers must be a list of strings")
    return tuple(markers)
