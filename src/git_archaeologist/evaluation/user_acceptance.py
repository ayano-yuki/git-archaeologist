"""Phase 5 human user-acceptance evaluation forms and reports.

The builder consumes checked-in form definitions and human review records. It
does not collect external artifacts, train models, or run heavyweight inference.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


USER_ACCEPTANCE_SCHEMA_VERSION = "phase5-user-acceptance-v1"
USER_ACCEPTANCE_REPORT_VERSION = "phase5-user-acceptance-report-v1"
DEFAULT_USER_ACCEPTANCE_DATA_DIR = Path("data/baseline-rag/eval/user-acceptance")


class AcceptanceDimension(StrEnum):
    """Human-scored dimensions required for Phase 5 acceptance."""

    ACCURACY = "accuracy"
    EVIDENCE_SUFFICIENCY = "evidence_sufficiency"
    CLARITY = "clarity"
    UNNECESSARY_WARNING = "unnecessary_warning"
    INVESTIGATION_TIME_SAVED = "investigation_time_saved"


class ReleaseDecision(StrEnum):
    """Release readiness derived from human review records."""

    READY = "ready"
    NEEDS_FOLLOW_UP = "needs_follow_up"
    BLOCKED = "blocked"


class UnresolvedIssueSeverity(StrEnum):
    """Severity assigned to deterministic unresolved-issue markers."""

    FOLLOW_UP = "follow_up"
    WARNING = "warning"
    BLOCKER = "blocker"


@dataclass(frozen=True)
class RubricItem:
    """One scored human-evaluation dimension."""

    dimension: AcceptanceDimension
    label: str
    prompt: str
    min_score: int
    max_score: int
    pass_score: int
    anchors: Mapping[int, str]

    def __post_init__(self) -> None:
        if self.min_score >= self.max_score:
            raise ValueError("rubric min_score must be lower than max_score")
        if self.pass_score < self.min_score or self.pass_score > self.max_score:
            raise ValueError("rubric pass_score must be inside score range")
        if not self.anchors:
            raise ValueError("rubric anchors must not be empty")
        for score in self.anchors:
            if score < self.min_score or score > self.max_score:
                raise ValueError(f"anchor score out of range: {score}")

    def to_dict(self) -> dict[str, object]:
        return {
            "dimension": self.dimension.value,
            "label": self.label,
            "prompt": self.prompt,
            "min_score": self.min_score,
            "max_score": self.max_score,
            "pass_score": self.pass_score,
            "anchors": {str(score): text for score, text in sorted(self.anchors.items())},
        }


@dataclass(frozen=True)
class AcceptanceThresholds:
    """Human acceptance gates fixed before collecting review results."""

    minimum_average_score: float
    minimum_dimension_average: Mapping[AcceptanceDimension, float]
    maximum_critical_misinformation: int
    maximum_unnecessary_warning_rate: float
    minimum_investigation_time_saved_ratio: float

    def __post_init__(self) -> None:
        _validate_rate(
            "maximum_unnecessary_warning_rate",
            self.maximum_unnecessary_warning_rate,
        )
        _validate_rate(
            "minimum_investigation_time_saved_ratio",
            self.minimum_investigation_time_saved_ratio,
        )
        if self.minimum_average_score <= 0:
            raise ValueError("minimum_average_score must be positive")
        if self.maximum_critical_misinformation < 0:
            raise ValueError("maximum_critical_misinformation must not be negative")
        for dimension in AcceptanceDimension:
            if dimension not in self.minimum_dimension_average:
                raise ValueError(f"missing threshold for {dimension.value}")

    def to_dict(self) -> dict[str, object]:
        return {
            "minimum_average_score": self.minimum_average_score,
            "minimum_dimension_average": {
                dimension.value: score
                for dimension, score in sorted(
                    self.minimum_dimension_average.items(),
                    key=lambda item: item[0].value,
                )
            },
            "maximum_critical_misinformation": self.maximum_critical_misinformation,
            "maximum_unnecessary_warning_rate": self.maximum_unnecessary_warning_rate,
            "minimum_investigation_time_saved_ratio": self.minimum_investigation_time_saved_ratio,
        }


@dataclass(frozen=True)
class UserAcceptanceCase:
    """One manually reviewed user-acceptance scenario."""

    case_id: str
    scenario: str
    task: str
    required_dimensions: tuple[AcceptanceDimension, ...]
    expected_evidence_ids: tuple[str, ...]
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id must be non-empty")
        if not self.required_dimensions:
            raise ValueError("required_dimensions must not be empty")
        object.__setattr__(self, "required_dimensions", tuple(self.required_dimensions))
        object.__setattr__(self, "expected_evidence_ids", tuple(self.expected_evidence_ids))

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "scenario": self.scenario,
            "task": self.task,
            "required_dimensions": [
                dimension.value for dimension in self.required_dimensions
            ],
            "expected_evidence_ids": list(self.expected_evidence_ids),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class UserAcceptanceForm:
    """Frozen form definition used by human reviewers."""

    schema_version: str
    form_id: str
    rubric: tuple[RubricItem, ...]
    thresholds: AcceptanceThresholds
    cases: tuple[UserAcceptanceCase, ...]
    instructions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != USER_ACCEPTANCE_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        rubric_dimensions = {item.dimension for item in self.rubric}
        missing = set(AcceptanceDimension) - rubric_dimensions
        if missing:
            missing_text = ", ".join(sorted(dimension.value for dimension in missing))
            raise ValueError(f"rubric missing dimensions: {missing_text}")
        object.__setattr__(self, "rubric", tuple(self.rubric))
        object.__setattr__(self, "cases", tuple(self.cases))
        object.__setattr__(self, "instructions", tuple(self.instructions))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "form_id": self.form_id,
            "rubric": [item.to_dict() for item in self.rubric],
            "thresholds": self.thresholds.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
            "instructions": list(self.instructions),
        }


@dataclass(frozen=True)
class HumanEvaluationRecord:
    """One completed human review form, identified by pseudonymous evaluator ID."""

    record_id: str
    case_id: str
    evaluator_id: str
    evaluated_at: str
    scores: Mapping[AcceptanceDimension, float]
    warning_count: int
    unnecessary_warning_count: int
    critical_misinformation_count: int
    investigation_minutes_without_tool: float
    investigation_minutes_with_tool: float
    comments: str

    def __post_init__(self) -> None:
        if not self.record_id or not self.case_id or not self.evaluator_id:
            raise ValueError("record_id, case_id, and evaluator_id must be non-empty")
        if self.warning_count < 0 or self.unnecessary_warning_count < 0:
            raise ValueError("warning counts must not be negative")
        if self.unnecessary_warning_count > self.warning_count:
            raise ValueError("unnecessary_warning_count cannot exceed warning_count")
        if self.critical_misinformation_count < 0:
            raise ValueError("critical_misinformation_count must not be negative")
        if self.investigation_minutes_without_tool <= 0:
            raise ValueError("investigation_minutes_without_tool must be positive")
        if self.investigation_minutes_with_tool < 0:
            raise ValueError("investigation_minutes_with_tool must not be negative")
        for dimension in AcceptanceDimension:
            if dimension not in self.scores:
                raise ValueError(f"missing score for {dimension.value}")

    @property
    def unnecessary_warning_rate(self) -> float:
        if self.warning_count == 0:
            return 0.0
        return self.unnecessary_warning_count / self.warning_count

    @property
    def investigation_time_saved_ratio(self) -> float:
        saved = self.investigation_minutes_without_tool - self.investigation_minutes_with_tool
        return saved / self.investigation_minutes_without_tool

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "case_id": self.case_id,
            "evaluator_id": self.evaluator_id,
            "evaluated_at": self.evaluated_at,
            "scores": {
                dimension.value: score
                for dimension, score in sorted(
                    self.scores.items(),
                    key=lambda item: item[0].value,
                )
            },
            "warning_count": self.warning_count,
            "unnecessary_warning_count": self.unnecessary_warning_count,
            "critical_misinformation_count": self.critical_misinformation_count,
            "investigation_minutes_without_tool": self.investigation_minutes_without_tool,
            "investigation_minutes_with_tool": self.investigation_minutes_with_tool,
            "comments": self.comments,
        }


@dataclass(frozen=True)
class ThresholdResult:
    """One pass/fail threshold check."""

    threshold_id: str
    passed: bool
    observed: float
    limit: float
    comparator: str
    details: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class UnresolvedIssue:
    """Issue extracted from reviewer comments."""

    issue_id: str
    record_id: str
    case_id: str
    severity: UnresolvedIssueSeverity
    text: str

    def to_dict(self) -> dict[str, object]:
        return {
            "issue_id": self.issue_id,
            "record_id": self.record_id,
            "case_id": self.case_id,
            "severity": self.severity.value,
            "text": self.text,
        }


@dataclass(frozen=True)
class UserAcceptanceReport:
    """Serializable Phase 5 human acceptance report."""

    schema_version: str
    form_id: str
    generated_at: str
    release_decision: ReleaseDecision
    case_count: int
    record_count: int
    average_scores: Mapping[AcceptanceDimension, float]
    threshold_results: tuple[ThresholdResult, ...]
    unresolved_issues: tuple[UnresolvedIssue, ...]
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "threshold_results", tuple(self.threshold_results))
        object.__setattr__(self, "unresolved_issues", tuple(self.unresolved_issues))
        object.__setattr__(self, "notes", tuple(self.notes))

    @property
    def passed(self) -> bool:
        return self.release_decision is ReleaseDecision.READY


def load_user_acceptance_form(path: str | Path) -> UserAcceptanceForm:
    """Load a checked-in user-acceptance form JSON file."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("user acceptance form must be a JSON object")
    return user_acceptance_form_from_mapping(raw)


def load_human_evaluation_records(path: str | Path) -> tuple[HumanEvaluationRecord, ...]:
    """Load human review records from a JSONL file."""

    records: list[HumanEvaluationRecord] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, Mapping):
            raise ValueError(f"line {line_number}: record must be a JSON object")
        records.append(human_evaluation_record_from_mapping(raw))
    return tuple(records)


def user_acceptance_form_from_mapping(raw: Mapping[str, Any]) -> UserAcceptanceForm:
    """Convert a mapping into a validated form."""

    rubric = tuple(rubric_item_from_mapping(item) for item in _require_list(raw, "rubric"))
    thresholds = thresholds_from_mapping(_require_mapping(raw, "thresholds"))
    cases = tuple(case_from_mapping(item) for item in _require_list(raw, "cases"))
    instructions = tuple(str(item) for item in raw.get("instructions", ()))
    return UserAcceptanceForm(
        schema_version=_require_str(raw, "schema_version"),
        form_id=_require_str(raw, "form_id"),
        rubric=rubric,
        thresholds=thresholds,
        cases=cases,
        instructions=instructions,
    )


def rubric_item_from_mapping(raw: Mapping[str, Any]) -> RubricItem:
    """Convert one rubric item mapping."""

    anchors_raw = _require_mapping(raw, "anchors")
    anchors = {int(score): str(text) for score, text in anchors_raw.items()}
    return RubricItem(
        dimension=AcceptanceDimension(_require_str(raw, "dimension")),
        label=_require_str(raw, "label"),
        prompt=_require_str(raw, "prompt"),
        min_score=_require_int(raw, "min_score"),
        max_score=_require_int(raw, "max_score"),
        pass_score=_require_int(raw, "pass_score"),
        anchors=anchors,
    )


def thresholds_from_mapping(raw: Mapping[str, Any]) -> AcceptanceThresholds:
    """Convert threshold mapping."""

    dimension_raw = _require_mapping(raw, "minimum_dimension_average")
    return AcceptanceThresholds(
        minimum_average_score=_require_float(raw, "minimum_average_score"),
        minimum_dimension_average={
            AcceptanceDimension(key): float(value) for key, value in dimension_raw.items()
        },
        maximum_critical_misinformation=_require_int(
            raw,
            "maximum_critical_misinformation",
        ),
        maximum_unnecessary_warning_rate=_require_float(
            raw,
            "maximum_unnecessary_warning_rate",
        ),
        minimum_investigation_time_saved_ratio=_require_float(
            raw,
            "minimum_investigation_time_saved_ratio",
        ),
    )


def case_from_mapping(raw: Mapping[str, Any]) -> UserAcceptanceCase:
    """Convert one case mapping."""

    return UserAcceptanceCase(
        case_id=_require_str(raw, "case_id"),
        scenario=_require_str(raw, "scenario"),
        task=_require_str(raw, "task"),
        required_dimensions=tuple(
            AcceptanceDimension(item)
            for item in _require_list(raw, "required_dimensions")
        ),
        expected_evidence_ids=tuple(
            str(item) for item in raw.get("expected_evidence_ids", ())
        ),
        notes=str(raw.get("notes", "")),
    )


def human_evaluation_record_from_mapping(raw: Mapping[str, Any]) -> HumanEvaluationRecord:
    """Convert one human record mapping."""

    scores = {
        AcceptanceDimension(dimension): float(score)
        for dimension, score in _require_mapping(raw, "scores").items()
    }
    return HumanEvaluationRecord(
        record_id=_require_str(raw, "record_id"),
        case_id=_require_str(raw, "case_id"),
        evaluator_id=_require_str(raw, "evaluator_id"),
        evaluated_at=_require_str(raw, "evaluated_at"),
        scores=scores,
        warning_count=_require_int(raw, "warning_count"),
        unnecessary_warning_count=_require_int(raw, "unnecessary_warning_count"),
        critical_misinformation_count=_require_int(raw, "critical_misinformation_count"),
        investigation_minutes_without_tool=_require_float(
            raw,
            "investigation_minutes_without_tool",
        ),
        investigation_minutes_with_tool=_require_float(
            raw,
            "investigation_minutes_with_tool",
        ),
        comments=_require_str(raw, "comments"),
    )


def build_user_acceptance_report(
    form: UserAcceptanceForm,
    records: Sequence[HumanEvaluationRecord],
    *,
    generated_at: datetime | None = None,
) -> UserAcceptanceReport:
    """Build a deterministic user-acceptance report from human records."""

    if not records:
        raise ValueError("records must not be empty")
    timestamp = generated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("generated_at must include a timezone")
    _validate_records_against_form(form, records)

    average_scores = _average_scores(records)
    threshold_results = _threshold_results(form.thresholds, records, average_scores)
    unresolved_issues = extract_unresolved_issues(records)
    release_decision = decide_release(threshold_results, unresolved_issues)

    return UserAcceptanceReport(
        schema_version=USER_ACCEPTANCE_REPORT_VERSION,
        form_id=form.form_id,
        generated_at=timestamp.astimezone(timezone.utc).isoformat(),
        release_decision=release_decision,
        case_count=len(form.cases),
        record_count=len(records),
        average_scores=average_scores,
        threshold_results=threshold_results,
        unresolved_issues=unresolved_issues,
        notes=(
            "Human acceptance records are structured scores plus deterministic comment markers.",
            "The report builder does not collect external data, train models, or run model inference.",
        ),
    )


def extract_unresolved_issues(
    records: Sequence[HumanEvaluationRecord],
) -> tuple[UnresolvedIssue, ...]:
    """Extract unresolved issues from reviewer comments using stable markers."""

    issues: list[UnresolvedIssue] = []
    for record in records:
        for line_index, line in enumerate(record.comments.splitlines(), start=1):
            text = _extract_issue_text(line)
            if text is None:
                continue
            severity = _issue_severity(text)
            issues.append(
                UnresolvedIssue(
                    issue_id=f"{record.record_id}-issue-{line_index}",
                    record_id=record.record_id,
                    case_id=record.case_id,
                    severity=severity,
                    text=text,
                )
            )
    return tuple(issues)


def decide_release(
    threshold_results: Sequence[ThresholdResult],
    unresolved_issues: Sequence[UnresolvedIssue],
) -> ReleaseDecision:
    """Return release readiness from thresholds and unresolved issues."""

    if any(not result.passed for result in threshold_results):
        return ReleaseDecision.BLOCKED
    if any(issue.severity is UnresolvedIssueSeverity.BLOCKER for issue in unresolved_issues):
        return ReleaseDecision.BLOCKED
    if unresolved_issues:
        return ReleaseDecision.NEEDS_FOLLOW_UP
    return ReleaseDecision.READY


def user_acceptance_report_to_dict(report: UserAcceptanceReport) -> dict[str, object]:
    """Return a JSON-friendly report."""

    return {
        "schema_version": report.schema_version,
        "form_id": report.form_id,
        "generated_at": report.generated_at,
        "release_decision": report.release_decision.value,
        "passed": report.passed,
        "case_count": report.case_count,
        "record_count": report.record_count,
        "average_scores": {
            dimension.value: score
            for dimension, score in sorted(
                report.average_scores.items(),
                key=lambda item: item[0].value,
            )
        },
        "threshold_results": [
            result.to_dict() for result in report.threshold_results
        ],
        "unresolved_issues": [
            issue.to_dict() for issue in report.unresolved_issues
        ],
        "notes": list(report.notes),
    }


def user_acceptance_report_to_json(report: UserAcceptanceReport) -> str:
    """Return formatted JSON for the acceptance report."""

    return json.dumps(user_acceptance_report_to_dict(report), ensure_ascii=False, indent=2)


def user_acceptance_summary_to_markdown(report: UserAcceptanceReport) -> str:
    """Return a compact human-readable summary."""

    lines = [
        "# Phase 5 User Acceptance",
        "",
        f"- Form: `{report.form_id}`",
        f"- Decision: `{report.release_decision.value}`",
        f"- Generated at: `{report.generated_at}`",
        f"- Records: `{report.record_count}` across `{report.case_count}` cases",
        "",
        "| Dimension | Average score |",
        "| --- | ---: |",
    ]
    for dimension, score in sorted(report.average_scores.items(), key=lambda item: item[0].value):
        lines.append(f"| {dimension.value} | {score:.2f} |")
    lines.extend(["", "## Thresholds", ""])
    for result in report.threshold_results:
        marker = "passed" if result.passed else "failed"
        lines.append(
            f"- `{result.threshold_id}` {marker}: observed {result.observed:.3g} "
            f"{result.comparator} {result.limit:.3g}"
        )
    if report.unresolved_issues:
        lines.extend(["", "## Unresolved Issues", ""])
        for issue in report.unresolved_issues:
            lines.append(f"- `{issue.severity.value}` {issue.case_id}: {issue.text}")
    return "\n".join(lines) + "\n"


def write_user_acceptance_report(
    report: UserAcceptanceReport,
    *,
    output_dir: str | Path,
    json_filename: str = "user-acceptance-report.json",
    markdown_filename: str = "user-acceptance-report.md",
) -> tuple[Path, Path]:
    """Write JSON and Markdown report outputs under output_dir."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / json_filename
    markdown_path = root / markdown_filename
    json_path.write_text(user_acceptance_report_to_json(report) + "\n", encoding="utf-8")
    markdown_path.write_text(
        user_acceptance_summary_to_markdown(report),
        encoding="utf-8",
    )
    return json_path, markdown_path


def default_user_acceptance_output_dir(
    *,
    data_root: str | Path = "data",
) -> Path:
    """Return the conventional checked-in user-acceptance evaluation directory."""

    return Path(data_root) / "baseline-rag" / "eval" / "user-acceptance"


def _validate_records_against_form(
    form: UserAcceptanceForm,
    records: Sequence[HumanEvaluationRecord],
) -> None:
    cases = {case.case_id: case for case in form.cases}
    rubric_by_dimension = {item.dimension: item for item in form.rubric}
    for record in records:
        if record.case_id not in cases:
            raise ValueError(f"record references unknown case: {record.case_id}")
        case = cases[record.case_id]
        for dimension in case.required_dimensions:
            if dimension not in record.scores:
                raise ValueError(
                    f"{record.record_id} missing required dimension {dimension.value}"
                )
        for dimension, score in record.scores.items():
            rubric = rubric_by_dimension[dimension]
            if score < rubric.min_score or score > rubric.max_score:
                raise ValueError(
                    f"{record.record_id} score for {dimension.value} is outside rubric range"
                )


def _average_scores(
    records: Sequence[HumanEvaluationRecord],
) -> dict[AcceptanceDimension, float]:
    averages: dict[AcceptanceDimension, float] = {}
    for dimension in AcceptanceDimension:
        values = [float(record.scores[dimension]) for record in records]
        averages[dimension] = sum(values) / len(values)
    return averages


def _threshold_results(
    thresholds: AcceptanceThresholds,
    records: Sequence[HumanEvaluationRecord],
    average_scores: Mapping[AcceptanceDimension, float],
) -> tuple[ThresholdResult, ...]:
    overall_average = sum(average_scores.values()) / len(average_scores)
    total_critical = sum(record.critical_misinformation_count for record in records)
    total_warnings = sum(record.warning_count for record in records)
    total_unnecessary = sum(record.unnecessary_warning_count for record in records)
    unnecessary_warning_rate = 0.0 if total_warnings == 0 else total_unnecessary / total_warnings
    average_time_saved = sum(record.investigation_time_saved_ratio for record in records) / len(records)

    results = [
        ThresholdResult(
            threshold_id="minimum_average_score",
            passed=overall_average >= thresholds.minimum_average_score,
            observed=overall_average,
            limit=thresholds.minimum_average_score,
            comparator=">=",
            details="Average across all required user-acceptance dimensions.",
        ),
        ThresholdResult(
            threshold_id="maximum_critical_misinformation",
            passed=total_critical <= thresholds.maximum_critical_misinformation,
            observed=float(total_critical),
            limit=float(thresholds.maximum_critical_misinformation),
            comparator="<=",
            details="Critical misleading explanations across all records.",
        ),
        ThresholdResult(
            threshold_id="maximum_unnecessary_warning_rate",
            passed=unnecessary_warning_rate <= thresholds.maximum_unnecessary_warning_rate,
            observed=unnecessary_warning_rate,
            limit=thresholds.maximum_unnecessary_warning_rate,
            comparator="<=",
            details="Unnecessary warnings divided by total warnings.",
        ),
        ThresholdResult(
            threshold_id="minimum_investigation_time_saved_ratio",
            passed=average_time_saved >= thresholds.minimum_investigation_time_saved_ratio,
            observed=average_time_saved,
            limit=thresholds.minimum_investigation_time_saved_ratio,
            comparator=">=",
            details="Average relative investigation time saved by the tool.",
        ),
    ]
    for dimension, limit in sorted(
        thresholds.minimum_dimension_average.items(),
        key=lambda item: item[0].value,
    ):
        observed = average_scores[dimension]
        results.append(
            ThresholdResult(
                threshold_id=f"minimum_{dimension.value}_average",
                passed=observed >= limit,
                observed=observed,
                limit=limit,
                comparator=">=",
                details=f"Average score for {dimension.value}.",
            )
        )
    return tuple(results)


_ISSUE_MARKER_PATTERN = re.compile(
    r"^\s*(?:unresolved|issue|follow[- ]?up|blocker)\s*:\s*(?P<text>.+?)\s*$",
    re.IGNORECASE,
)


def _extract_issue_text(line: str) -> str | None:
    match = _ISSUE_MARKER_PATTERN.match(line)
    if not match:
        return None
    text = match.group("text").strip()
    return text or None


def _issue_severity(text: str) -> UnresolvedIssueSeverity:
    lowered = text.lower()
    if "blocker" in lowered or "critical" in lowered or "must fix" in lowered:
        return UnresolvedIssueSeverity.BLOCKER
    if "warning" in lowered or "false positive" in lowered:
        return UnresolvedIssueSeverity.WARNING
    return UnresolvedIssueSeverity.FOLLOW_UP


def _validate_rate(name: str, value: float) -> None:
    if value < 0 or value > 1:
        raise ValueError(f"{name} must be in the range [0, 1]")


def _require_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _require_list(raw: Mapping[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _require_float(raw: Mapping[str, Any], key: str) -> float:
    value = raw.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--form",
        type=Path,
        default=DEFAULT_USER_ACCEPTANCE_DATA_DIR / "user-acceptance-form.json",
    )
    parser.add_argument(
        "--records",
        type=Path,
        default=DEFAULT_USER_ACCEPTANCE_DATA_DIR / "sample-evaluations.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_USER_ACCEPTANCE_DATA_DIR,
    )
    parser.add_argument("--no-write", action="store_true", help="print only; do not write report files")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = build_user_acceptance_report(
        load_user_acceptance_form(args.form),
        load_human_evaluation_records(args.records),
    )
    payload = user_acceptance_report_to_dict(report)
    if not args.no_write:
        json_path, markdown_path = write_user_acceptance_report(
            report,
            output_dir=args.output_dir,
        )
        payload["output_paths"] = [str(json_path), str(markdown_path)]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.release_decision is not ReleaseDecision.BLOCKED else 1


if __name__ == "__main__":
    raise SystemExit(main())
