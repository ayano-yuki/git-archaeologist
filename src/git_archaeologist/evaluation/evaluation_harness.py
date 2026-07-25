"""Evaluation metrics that keep retrieval and answer failures separate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class FailureStage(StrEnum):
    """Where an evaluation case failed."""

    TARGET_RESOLUTION = "target_resolution"
    SEARCH = "search"
    RERANK = "rerank"
    GENERATION = "generation"
    CITATION_VERIFICATION = "citation_verification"


@dataclass(frozen=True)
class TargetResolutionEvaluation:
    """Input/target resolution outcome."""

    case_id: str
    expected_target_id: str | None
    predicted_target_id: str | None
    should_resolve: bool = True

    @property
    def is_correct(self) -> bool:
        if not self.should_resolve:
            return self.predicted_target_id is None
        return self.expected_target_id == self.predicted_target_id


@dataclass(frozen=True)
class RetrievalEvaluation:
    """Evidence retrieval outcome."""

    case_id: str
    required_evidence_ids: tuple[str, ...]
    retrieved_evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_evidence_ids", tuple(self.required_evidence_ids))
        object.__setattr__(self, "retrieved_evidence_ids", tuple(self.retrieved_evidence_ids))

    def recall_at(self, k: int) -> float:
        if not self.required_evidence_ids:
            return 1.0
        retrieved = set(self.retrieved_evidence_ids[:k])
        required = set(self.required_evidence_ids)
        return len(required & retrieved) / len(required)

    def reciprocal_rank(self) -> float:
        required = set(self.required_evidence_ids)
        for rank, evidence_id in enumerate(self.retrieved_evidence_ids, start=1):
            if evidence_id in required:
                return 1 / rank
        return 0.0


@dataclass(frozen=True)
class AnswerEvaluation:
    """Answer generation and verification outcome."""

    case_id: str
    expected_risk_label: str
    predicted_risk_label: str
    should_abstain: bool
    abstained: bool
    unsupported_claim_count: int
    citation_failure_count: int

    @property
    def risk_label_correct(self) -> bool:
        return self.expected_risk_label == self.predicted_risk_label

    @property
    def abstention_correct(self) -> bool:
        return self.should_abstain == self.abstained


@dataclass(frozen=True)
class FailureClassification:
    """Failure bucket for report triage."""

    case_id: str
    stage: FailureStage
    reason: str


@dataclass(frozen=True)
class EvaluationReport:
    """MVP evaluation report split into search and answer sections."""

    target_resolution_accuracy: float
    evidence_recall_at_k: float
    mean_reciprocal_rank: float
    citation_consistency_rate: float
    unsupported_claim_rate: float
    abstention_accuracy: float
    risk_warning_precision: float
    failures: tuple[FailureClassification, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "failures", tuple(self.failures))

    def to_dict(self) -> dict[str, object]:
        return {
            "search_metrics": {
                "target_resolution_accuracy": self.target_resolution_accuracy,
                "evidence_recall_at_k": self.evidence_recall_at_k,
                "mean_reciprocal_rank": self.mean_reciprocal_rank,
            },
            "answer_metrics": {
                "citation_consistency_rate": self.citation_consistency_rate,
                "unsupported_claim_rate": self.unsupported_claim_rate,
                "abstention_accuracy": self.abstention_accuracy,
                "risk_warning_precision": self.risk_warning_precision,
            },
            "failures": [
                {"case_id": failure.case_id, "stage": failure.stage.value, "reason": failure.reason}
                for failure in self.failures
            ],
        }


def build_evaluation_report(
    *,
    target_cases: tuple[TargetResolutionEvaluation, ...],
    retrieval_cases: tuple[RetrievalEvaluation, ...],
    answer_cases: tuple[AnswerEvaluation, ...],
    k: int = 5,
) -> EvaluationReport:
    """Compute MVP metrics and classify failures without mixing stages."""

    failures: list[FailureClassification] = []
    for case in target_cases:
        if not case.is_correct:
            failures.append(FailureClassification(case.case_id, FailureStage.TARGET_RESOLUTION, "target mismatch"))
    for case in retrieval_cases:
        if case.recall_at(k) < 1:
            failures.append(FailureClassification(case.case_id, FailureStage.SEARCH, f"missing evidence at {k}"))
        if case.required_evidence_ids and case.reciprocal_rank() == 0:
            failures.append(FailureClassification(case.case_id, FailureStage.RERANK, "required evidence never ranked"))
    for case in answer_cases:
        if case.unsupported_claim_count:
            failures.append(FailureClassification(case.case_id, FailureStage.GENERATION, "unsupported claims present"))
        if case.citation_failure_count:
            failures.append(FailureClassification(case.case_id, FailureStage.CITATION_VERIFICATION, "citation verification failed"))

    return EvaluationReport(
        target_resolution_accuracy=_mean(tuple(1.0 if case.is_correct else 0.0 for case in target_cases)),
        evidence_recall_at_k=_mean(tuple(case.recall_at(k) for case in retrieval_cases)),
        mean_reciprocal_rank=_mean(tuple(case.reciprocal_rank() for case in retrieval_cases)),
        citation_consistency_rate=_mean(tuple(1.0 if case.citation_failure_count == 0 else 0.0 for case in answer_cases)),
        unsupported_claim_rate=_mean(tuple(1.0 if case.unsupported_claim_count else 0.0 for case in answer_cases)),
        abstention_accuracy=_mean(tuple(1.0 if case.abstention_correct else 0.0 for case in answer_cases)),
        risk_warning_precision=_risk_warning_precision(answer_cases),
        failures=tuple(failures),
    )


def _risk_warning_precision(answer_cases: tuple[AnswerEvaluation, ...]) -> float:
    predicted_risk = [case for case in answer_cases if case.predicted_risk_label == "risk_found"]
    if not predicted_risk:
        return 1.0
    true_positive = sum(1 for case in predicted_risk if case.expected_risk_label == "risk_found")
    return true_positive / len(predicted_risk)


def _mean(values: tuple[float, ...]) -> float:
    if not values:
        return 1.0
    return sum(values) / len(values)
