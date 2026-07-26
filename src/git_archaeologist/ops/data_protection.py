"""Data inventory, deletion planning, and backup planning for local runtime data."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from enum import StrEnum
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterable, Sequence


DEFAULT_DATA_ROOT = Path("data")
SECRET_FIELD_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"authorization",
        r"raw[_-]?token",
        r"access[_-]?token",
        r"refresh[_-]?token",
        r"auth[_-]?token",
        r"secret",
        r"private[_-]?key",
        r"password",
        r"credential",
    )
)
TOKENIZER_ASSET_NAMES = frozenset(
    {
        "added_tokens.json",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
    }
)


class DataProtectionStatus(StrEnum):
    """Operator-facing data protection status."""

    READY = "ready"
    BLOCKED = "blocked"
    EXECUTED = "executed"


class ProtectedDataCategory(StrEnum):
    """Known local data categories that can contain repository-derived content."""

    RAW = "raw"
    RUNS = "runs"
    MODELS = "models"
    EVAL = "eval"


@dataclass(frozen=True)
class ProtectedDataPath:
    """One local path that may contain repository-derived data."""

    category: ProtectedDataCategory
    path: str
    exists: bool
    file_count: int
    byte_count: int
    deletable: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["category"] = self.category.value
        return payload


@dataclass(frozen=True)
class SecretLikeFinding:
    """A secret-like field name without exposing the field value."""

    path: str
    field_path: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DataProtectionInventoryReport:
    """Safe inventory of repository-derived local data."""

    status: DataProtectionStatus
    repository_id: str
    repository_slug: str
    data_root: str
    paths: tuple[ProtectedDataPath, ...]
    secret_like_findings: tuple[SecretLikeFinding, ...]
    redaction_blocked: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "paths", tuple(self.paths))
        object.__setattr__(self, "secret_like_findings", tuple(self.secret_like_findings))

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "repository_id": self.repository_id,
            "repository_slug": self.repository_slug,
            "data_root": self.data_root,
            "paths": [path.to_dict() for path in self.paths],
            "secret_like_findings": [finding.to_dict() for finding in self.secret_like_findings],
            "redaction_blocked": self.redaction_blocked,
        }


@dataclass(frozen=True)
class DeletePlanReport:
    """Dry-run-first deletion plan for repository-derived data."""

    status: DataProtectionStatus
    repository_id: str
    dry_run: bool
    target_paths: tuple[str, ...]
    blocked_paths: tuple[str, ...]
    executed_paths: tuple[str, ...]
    secret_like_findings: tuple[SecretLikeFinding, ...]
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_paths", tuple(self.target_paths))
        object.__setattr__(self, "blocked_paths", tuple(self.blocked_paths))
        object.__setattr__(self, "executed_paths", tuple(self.executed_paths))
        object.__setattr__(self, "secret_like_findings", tuple(self.secret_like_findings))

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "repository_id": self.repository_id,
            "dry_run": self.dry_run,
            "target_paths": list(self.target_paths),
            "blocked_paths": list(self.blocked_paths),
            "executed_paths": list(self.executed_paths),
            "secret_like_findings": [finding.to_dict() for finding in self.secret_like_findings],
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BackupPlanReport:
    """Backup plan for repository-derived data without copying by default."""

    status: DataProtectionStatus
    repository_id: str
    dry_run: bool
    source_paths: tuple[str, ...]
    backup_root: str
    manifest_path: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_paths", tuple(self.source_paths))

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def build_data_protection_inventory(
    *,
    repository_id: str = "react/react",
    data_root: Path = DEFAULT_DATA_ROOT,
) -> DataProtectionInventoryReport:
    """List raw, run, model, and eval paths for one repository."""

    root = data_root.resolve()
    repository_slug = repository_id_to_slug(repository_id)
    paths = tuple(_candidate_paths(root, repository_id=repository_id))
    findings = tuple(find_secret_like_fields(path.path for path in paths if path.exists))
    return DataProtectionInventoryReport(
        status=DataProtectionStatus.BLOCKED if findings else DataProtectionStatus.READY,
        repository_id=repository_id,
        repository_slug=repository_slug,
        data_root=str(root),
        paths=paths,
        secret_like_findings=findings,
        redaction_blocked=bool(findings),
    )


def build_delete_plan(
    *,
    repository_id: str = "react/react",
    data_root: Path = DEFAULT_DATA_ROOT,
    execute: bool = False,
    confirm_repository_id: str | None = None,
) -> DeletePlanReport:
    """Build or execute a repository-scoped deletion plan."""

    inventory = build_data_protection_inventory(repository_id=repository_id, data_root=data_root)
    target_paths = tuple(path.path for path in inventory.paths if path.exists and path.deletable)
    blocked_paths = tuple(_paths_outside_boundary(target_paths, data_root.resolve()))
    if inventory.secret_like_findings:
        return DeletePlanReport(
            status=DataProtectionStatus.BLOCKED,
            repository_id=repository_id,
            dry_run=not execute,
            target_paths=target_paths,
            blocked_paths=blocked_paths,
            executed_paths=(),
            secret_like_findings=inventory.secret_like_findings,
            reason="Secret-like fields were detected; values are suppressed and deletion is blocked.",
        )
    if blocked_paths:
        return DeletePlanReport(
            status=DataProtectionStatus.BLOCKED,
            repository_id=repository_id,
            dry_run=not execute,
            target_paths=target_paths,
            blocked_paths=blocked_paths,
            executed_paths=(),
            secret_like_findings=(),
            reason="One or more target paths escaped the configured data root.",
        )
    if not execute:
        return DeletePlanReport(
            status=DataProtectionStatus.READY,
            repository_id=repository_id,
            dry_run=True,
            target_paths=target_paths,
            blocked_paths=(),
            executed_paths=(),
            secret_like_findings=(),
            reason="Dry-run delete plan only; no files were removed.",
        )
    if confirm_repository_id != repository_id:
        return DeletePlanReport(
            status=DataProtectionStatus.BLOCKED,
            repository_id=repository_id,
            dry_run=False,
            target_paths=target_paths,
            blocked_paths=(),
            executed_paths=(),
            secret_like_findings=(),
            reason="Deletion execution requires --confirm-repository-id to match --repository-id.",
        )

    executed: list[str] = []
    for target_path in target_paths:
        path = Path(target_path)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        executed.append(target_path)
    return DeletePlanReport(
        status=DataProtectionStatus.EXECUTED,
        repository_id=repository_id,
        dry_run=False,
        target_paths=target_paths,
        blocked_paths=(),
        executed_paths=tuple(executed),
        secret_like_findings=(),
        reason="Repository-scoped data paths were deleted after explicit confirmation.",
    )


def build_backup_plan(
    *,
    repository_id: str = "react/react",
    data_root: Path = DEFAULT_DATA_ROOT,
    backup_root: Path | None = None,
) -> BackupPlanReport:
    """Describe backup inputs and destination without copying data."""

    root = data_root.resolve()
    repository_slug = repository_id_to_slug(repository_id)
    inventory = build_data_protection_inventory(repository_id=repository_id, data_root=data_root)
    source_paths = tuple(path.path for path in inventory.paths if path.exists)
    resolved_backup_root = (
        backup_root.resolve()
        if backup_root is not None
        else root / "local-runtime" / "runs" / "data-protection-backups" / repository_slug
    )
    return BackupPlanReport(
        status=DataProtectionStatus.BLOCKED if inventory.secret_like_findings else DataProtectionStatus.READY,
        repository_id=repository_id,
        dry_run=True,
        source_paths=source_paths,
        backup_root=str(resolved_backup_root),
        manifest_path=str(resolved_backup_root / "backup-manifest.json"),
        reason=(
            "Secret-like fields were detected; values are suppressed and backup is blocked."
            if inventory.secret_like_findings
            else "Dry-run backup plan only; no files were copied."
        ),
    )


def find_secret_like_fields(paths: Iterable[str | Path]) -> tuple[SecretLikeFinding, ...]:
    """Detect secret-like field names without returning values."""

    findings: list[SecretLikeFinding] = []
    for root_path in paths:
        path = Path(root_path)
        files = path.rglob("*") if path.is_dir() else (path,)
        for file_path in files:
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() == ".json":
                findings.extend(_json_secret_findings(file_path))
            elif file_path.suffix.lower() in {".jsonl", ".md", ".txt", ".log"}:
                findings.extend(_text_secret_findings(file_path))
    return tuple(findings)


def repository_id_to_slug(repository_id: str) -> str:
    """Return a filesystem-friendly repository slug."""

    owner, repo = _split_repository_id(repository_id)
    return f"{owner}-{repo}"


def report_to_json(
    report: DataProtectionInventoryReport | DeletePlanReport | BackupPlanReport,
) -> str:
    """Serialize a data protection report."""

    return json.dumps(report.to_dict(), ensure_ascii=True, indent=2)


def _candidate_paths(root: Path, *, repository_id: str) -> tuple[ProtectedDataPath, ...]:
    owner, repo = _split_repository_id(repository_id)
    repository_slug = repository_id_to_slug(repository_id)
    candidates: list[tuple[ProtectedDataCategory, Path, bool]] = [
        (ProtectedDataCategory.RAW, root / "local-runtime" / "raw" / owner / repo, True),
    ]
    candidates.extend(
        (ProtectedDataCategory.RUNS, path, True)
        for path in sorted((root / "local-runtime" / "runs").glob(f"{repository_slug}*"))
    )
    for model_root in _model_roots(root):
        candidates.extend(
            (
                (ProtectedDataCategory.MODELS, model_root / "models", False),
                (ProtectedDataCategory.EVAL, model_root / "eval", False),
                (ProtectedDataCategory.RUNS, model_root / "runs", True),
            )
        )
    candidates.extend(
        (
            (ProtectedDataCategory.EVAL, root / "baseline-rag" / "eval", False),
            (ProtectedDataCategory.MODELS, root / "baseline-rag" / "models", False),
        )
    )
    unique: dict[str, ProtectedDataPath] = {}
    for category, path, deletable in candidates:
        protected_path = _protected_path(category, path, deletable=deletable)
        unique[protected_path.path] = protected_path
    return tuple(sorted(unique.values(), key=lambda item: (item.category.value, item.path)))


def _protected_path(category: ProtectedDataCategory, path: Path, *, deletable: bool) -> ProtectedDataPath:
    file_count, byte_count = _measure_path(path)
    return ProtectedDataPath(
        category=category,
        path=str(path.resolve()),
        exists=path.exists(),
        file_count=file_count,
        byte_count=byte_count,
        deletable=deletable,
    )


def _measure_path(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    files = tuple(item for item in path.rglob("*") if item.is_file()) if path.is_dir() else (path,)
    return len(files), sum(item.stat().st_size for item in files)


def _model_roots(root: Path) -> tuple[Path, ...]:
    if not root.exists():
        return ()
    reserved = {"baseline-rag", "local-runtime"}
    return tuple(
        path
        for path in sorted(root.iterdir())
        if path.is_dir() and path.name not in reserved
    )


def _json_secret_findings(path: Path) -> tuple[SecretLikeFinding, ...]:
    if path.name in TOKENIZER_ASSET_NAMES:
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _text_secret_findings(path)
    return tuple(_walk_json_for_secret_fields(payload, path=path, field_path="$"))


def _walk_json_for_secret_fields(
    value: Any,
    *,
    path: Path,
    field_path: str,
) -> Iterable[SecretLikeFinding]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{field_path}.{key}"
            if _is_secret_like(str(key)):
                yield SecretLikeFinding(
                    path=str(path.resolve()),
                    field_path=child_path,
                    reason="secret-like field name detected; value suppressed",
                )
            yield from _walk_json_for_secret_fields(child, path=path, field_path=child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_json_for_secret_fields(child, path=path, field_path=f"{field_path}[{index}]")


def _text_secret_findings(path: Path) -> tuple[SecretLikeFinding, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ()
    findings: list[SecretLikeFinding] = []
    pattern = re.compile(
        r"\s*([A-Za-z0-9_.-]*(?:raw[_-]?token|access[_-]?token|refresh[_-]?token|auth[_-]?token|secret|password|authorization|credential|private[_-]?key)[A-Za-z0-9_.-]*)\s*[:=]",
        re.IGNORECASE,
    )
    for line_number, line in enumerate(lines, start=1):
        key_match = pattern.match(line)
        if key_match:
            findings.append(
                SecretLikeFinding(
                    path=str(path.resolve()),
                    field_path=f"line:{line_number}:{key_match.group(1)}",
                    reason="secret-like field name detected; value suppressed",
                )
            )
    return tuple(findings)


def _is_secret_like(field_name: str) -> bool:
    return any(pattern.search(field_name) for pattern in SECRET_FIELD_PATTERNS)


def _paths_outside_boundary(paths: Iterable[str], boundary: Path) -> tuple[str, ...]:
    resolved_boundary = boundary.resolve()
    escaped: list[str] = []
    for path in paths:
        resolved_path = Path(path).resolve()
        if resolved_path != resolved_boundary and resolved_boundary not in resolved_path.parents:
            escaped.append(str(resolved_path))
    return tuple(escaped)


def _split_repository_id(repository_id: str) -> tuple[str, str]:
    parts = repository_id.split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError("repository_id must be in owner/repo form")
    return parts[0], parts[1]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inventory", action="store_true", help="print repository data inventory")
    mode.add_argument("--delete-plan", action="store_true", help="print or execute a repository-scoped delete plan")
    mode.add_argument("--backup-plan", action="store_true", help="print a backup plan")
    parser.add_argument("--repository-id", default="react/react")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--backup-root", type=Path, default=None)
    parser.add_argument("--execute", action="store_true", help="execute deletion; ignored for inventory and backup plan")
    parser.add_argument("--confirm-repository-id", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.delete_plan:
        report = build_delete_plan(
            repository_id=args.repository_id,
            data_root=args.data_root,
            execute=args.execute,
            confirm_repository_id=args.confirm_repository_id,
        )
    elif args.backup_plan:
        report = build_backup_plan(
            repository_id=args.repository_id,
            data_root=args.data_root,
            backup_root=args.backup_root,
        )
    else:
        report = build_data_protection_inventory(
            repository_id=args.repository_id,
            data_root=args.data_root,
        )
    print(report_to_json(report))
    return 0 if report.status is not DataProtectionStatus.BLOCKED else 1


if __name__ == "__main__":
    raise SystemExit(main())
