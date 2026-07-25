"""Phase2 quality triage, RAG ablation comparison, and SFT decision records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from git_archaeologist.evaluation.evaluation_harness import EvaluationReport, FailureClassification, FailureStage


class FailureResponsibility(StrEnum):
    """Owner area for a failure category."""

    COLLECTOR = "collector"
    NORMALIZER = "normalizer"
    SEARCH = "search"
    RAG = "rag"
    CHAT = "chat"
    EVALUATION = "evaluation"


@dataclass(frozen=True)
class FailurePattern:
    """Aggregated failure pattern with improvement ownership."""

    stage: FailureStage
    count: int
    responsibility: FailureResponsibility
    priority: str
    example_case_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["stage"] = self.stage.value
        payload["responsibility"] = self.responsibility.value
        return payload


@dataclass(frozen=True)
class FailureTaxonomy:
    """Prioritized summary of evaluation failures."""

    patterns: tuple[FailurePattern, ...]

    def to_dict(self) -> dict[str, object]:
        return {"patterns": [pattern.to_dict() for pattern in self.patterns]}


@dataclass(frozen=True)
class ExperimentRun:
    """One baseline or single-component RAG experiment."""

    name: str
    changed_component: str
    metrics: dict[str, float]


@dataclass(frozen=True)
class AblationResult:
    """Metric deltas for one RAG or prompt change."""

    name: str
    changed_component: str
    deltas: dict[str, float]
    verdict: str


@dataclass(frozen=True)
class SftDecisionRecord:
    """Evidence-backed decision about whether to start SFT."""

    decision: str
    reasons: tuple[str, ...]
    failure_examples: tuple[str, ...]
    metrics: dict[str, float]
    taxonomy: FailureTaxonomy

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["taxonomy"] = self.taxonomy.to_dict()
        return payload


def build_failure_taxonomy(report: EvaluationReport) -> FailureTaxonomy:
    grouped: dict[FailureStage, list[FailureClassification]] = {}
    for failure in report.failures:
        grouped.setdefault(failure.stage, []).append(failure)

    patterns = []
    for stage, failures in grouped.items():
        patterns.append(
            FailurePattern(
                stage=stage,
                count=len(failures),
                responsibility=_responsibility_for(stage),
                priority="high" if len(failures) >= 2 else "medium",
                example_case_ids=tuple(failure.case_id for failure in failures[:3]),
            )
        )
    return FailureTaxonomy(patterns=tuple(sorted(patterns, key=lambda pattern: (-pattern.count, pattern.stage.value))))


def compare_ablation(baseline: ExperimentRun, variants: tuple[ExperimentRun, ...]) -> tuple[AblationResult, ...]:
    """Compare one-component changes against a frozen baseline."""

    results: list[AblationResult] = []
    for variant in variants:
        deltas = {
            metric: variant.metrics.get(metric, 0.0) - baseline.metrics.get(metric, 0.0)
            for metric in sorted(set(baseline.metrics) | set(variant.metrics))
        }
        total_delta = sum(deltas.values())
        verdict = "improved" if total_delta > 0 else "regressed" if total_delta < 0 else "unchanged"
        results.append(
            AblationResult(
                name=variant.name,
                changed_component=variant.changed_component,
                deltas=deltas,
                verdict=verdict,
            )
        )
    return tuple(results)


def decide_sft_need(report: EvaluationReport, taxonomy: FailureTaxonomy) -> SftDecisionRecord:
    """Decide whether failures are answer-discipline problems suitable for SFT."""

    metrics = {
        "target_resolution_accuracy": report.target_resolution_accuracy,
        "evidence_recall_at_k": report.evidence_recall_at_k,
        "citation_consistency_rate": report.citation_consistency_rate,
        "unsupported_claim_rate": report.unsupported_claim_rate,
        "abstention_accuracy": report.abstention_accuracy,
        "risk_warning_precision": report.risk_warning_precision,
    }
    search_failure_count = sum(
        pattern.count
        for pattern in taxonomy.patterns
        if pattern.responsibility in {FailureResponsibility.COLLECTOR, FailureResponsibility.SEARCH}
    )
    generation_failure_count = sum(
        pattern.count for pattern in taxonomy.patterns if pattern.responsibility is FailureResponsibility.RAG
    )

    reasons: list[str] = []
    if search_failure_count:
        reasons.append("検索・収集側の失敗が残っているため、SFTよりRAG改善を優先する。")
    if report.citation_consistency_rate < 0.95:
        reasons.append("引用整合率が目標未満で、Citation VerifierとEvidence Pack改善が必要。")
    if report.unsupported_claim_rate > 0.05 and generation_failure_count >= 2 and search_failure_count == 0:
        reasons.append("根拠があるのに未支持主張が反復しており、回答規律SFTの候補になる。")
    if not reasons:
        reasons.append("主要指標がPhase2の暫定品質目標を満たしており、現時点ではSFTを見送る。")

    decision = "consider_sft" if any("SFTの候補" in reason for reason in reasons) else "defer_sft"
    return SftDecisionRecord(
        decision=decision,
        reasons=tuple(reasons),
        failure_examples=tuple(
            case_id for pattern in taxonomy.patterns for case_id in pattern.example_case_ids
        ),
        metrics=metrics,
        taxonomy=taxonomy,
    )


def _responsibility_for(stage: FailureStage) -> FailureResponsibility:
    if stage is FailureStage.TARGET_RESOLUTION:
        return FailureResponsibility.SEARCH
    if stage is FailureStage.SEARCH:
        return FailureResponsibility.SEARCH
    if stage is FailureStage.RERANK:
        return FailureResponsibility.RAG
    if stage is FailureStage.GENERATION:
        return FailureResponsibility.RAG
    if stage is FailureStage.CITATION_VERIFICATION:
        return FailureResponsibility.RAG
    return FailureResponsibility.EVALUATION
