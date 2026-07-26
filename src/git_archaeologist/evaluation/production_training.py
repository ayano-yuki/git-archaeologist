"""Production-data readiness checks for answer-discipline training."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
from pathlib import Path
import json
from typing import Iterable, Sequence

from git_archaeologist.evaluation.train_sft import (
    DEFAULT_PLAN_PATH,
    SFTDryRunReport,
    build_dry_run_report,
    dry_run_report_to_dict,
)


REQUIRED_PRODUCTION_ARTIFACT_KINDS = frozenset(
    {
        "commit",
        "pull_request",
        "issue",
        "review",
        "review_comment",
        "ci_run",
        "ci_job",
    }
)


@dataclass(frozen=True)
class ProductionCollectionSummary:
    """A collected production raw-data run under data/local-runtime/runs."""

    run_id: str
    repository_id: str
    passed: bool
    collected_artifact_count: int
    artifact_counts: dict[str, int]
    manifest_path: str

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ProductionCollectionSummary":
        return cls(
            run_id=str(payload["run_id"]),
            repository_id=str(payload["repository_id"]),
            passed=bool(payload["passed"]),
            collected_artifact_count=int(payload["collected_artifact_count"]),
            artifact_counts={str(key): int(value) for key, value in dict(payload["artifact_counts"]).items()},
            manifest_path=str(payload["manifest_path"]),
        )

    @property
    def artifact_kinds(self) -> frozenset[str]:
        return frozenset(self.artifact_counts)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProductionTrainingReadiness:
    """Gate report before using production data for QLoRA/SFT."""

    status: str
    repository_id: str
    production_run_count: int
    collected_artifact_count: int
    covered_artifact_kinds: tuple[str, ...]
    missing_artifact_kinds: tuple[str, ...]
    failed_run_ids: tuple[str, ...]
    dry_run: SFTDryRunReport
    execute_command: str

    @property
    def ready(self) -> bool:
        return self.status == "production_training_ready"

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["dry_run"] = dry_run_report_to_dict(self.dry_run)
        return payload


def discover_production_collection_summaries(
    runs_root: Path = Path("data/local-runtime/runs"),
) -> tuple[ProductionCollectionSummary, ...]:
    """Load passed and failed production collection summary files."""

    summaries: list[ProductionCollectionSummary] = []
    if not runs_root.exists():
        return ()
    for summary_path in sorted(runs_root.glob("*production*/collection-summary.json")):
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        summaries.append(ProductionCollectionSummary.from_dict(payload))
    return tuple(summaries)


def build_production_training_readiness(
    *,
    runs_root: Path = Path("data/local-runtime/runs"),
    plan_path: Path = DEFAULT_PLAN_PATH,
    required_artifact_kinds: Iterable[str] = REQUIRED_PRODUCTION_ARTIFACT_KINDS,
    dependency_names: tuple[str, ...] = (),
) -> ProductionTrainingReadiness:
    """Check production raw data, SFT data, runtime constraints, and command hints."""

    summaries = discover_production_collection_summaries(runs_root)
    dry_run = build_dry_run_report(plan_path, dependency_names=dependency_names)
    covered = frozenset(kind for summary in summaries for kind in summary.artifact_kinds)
    required = frozenset(required_artifact_kinds)
    missing = tuple(sorted(required - covered))
    failed = tuple(summary.run_id for summary in summaries if not summary.passed)
    repositories = {summary.repository_id for summary in summaries}
    repository_id = sorted(repositories)[0] if len(repositories) == 1 else "mixed-or-missing"
    collected_artifact_count = sum(summary.collected_artifact_count for summary in summaries if summary.passed)
    status = (
        "production_training_ready"
        if summaries
        and not missing
        and not failed
        and not dry_run.missing_optional_dependencies
        and dry_run.should_train
        and dry_run.record_count > 0
        else "production_training_blocked"
    )
    return ProductionTrainingReadiness(
        status=status,
        repository_id=repository_id,
        production_run_count=len(summaries),
        collected_artifact_count=collected_artifact_count,
        covered_artifact_kinds=tuple(sorted(covered)),
        missing_artifact_kinds=missing,
        failed_run_ids=failed,
        dry_run=dry_run,
        execute_command=(
            "uv --system-certs run --extra training python -m "
            f"git_archaeologist.evaluation.train_sft --plan {plan_path} --execute"
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=Path("data/local-runtime/runs"))
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument(
        "--require-training-dependencies",
        action="store_true",
        help="Require optional training modules instead of only validating data and plan shape.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    dependency_names = None
    if args.require_training_dependencies:
        from git_archaeologist.evaluation.train_sft import REQUIRED_TRAINING_MODULES

        dependency_names = REQUIRED_TRAINING_MODULES
    readiness = build_production_training_readiness(
        runs_root=args.runs_root,
        plan_path=args.plan,
        dependency_names=dependency_names or (),
    )
    print(json.dumps(readiness.to_dict(), ensure_ascii=False, indent=2))
    return 0 if readiness.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
