"""Repository collection configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from importlib import resources
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlparse


class ArtifactKind(str, Enum):
    """Artifact kinds that can be collected from a repository."""

    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    REVIEW = "review"
    REVIEW_COMMENT = "review_comment"
    ISSUE_COMMENT = "issue_comment"
    CI_RUN = "ci_run"
    CI_JOB = "ci_job"


@dataclass(frozen=True)
class HistoryWindow:
    """Closed collection window shared by repository artifacts."""

    since: datetime
    until: datetime

    def __post_init__(self) -> None:
        if self.since.tzinfo is None or self.since.utcoffset() is None:
            raise ValueError("history.since must include a timezone")
        if self.until.tzinfo is None or self.until.utcoffset() is None:
            raise ValueError("history.until must include a timezone")
        if self.since > self.until:
            raise ValueError("history.since must be before or equal to history.until")


@dataclass(frozen=True)
class ArtifactScope:
    """Collection scope for one artifact kind."""

    kind: ArtifactKind
    enabled: bool
    selectors: Mapping[str, Any]
    history_window: HistoryWindow | None = None

    def effective_history_window(self, repository_window: HistoryWindow) -> HistoryWindow:
        return self.history_window or repository_window


@dataclass(frozen=True)
class ExclusionRule:
    """Rule that removes known-unwanted artifacts from collection."""

    rule_id: str
    artifact_kinds: tuple[ArtifactKind, ...]
    field: str
    pattern: str
    reason: str


@dataclass(frozen=True)
class PrivateInfoPolicy:
    """Policy for private repository data and secret-like content."""

    repository_visibility: str
    allow_private_repository: bool
    store_raw_private_data: bool
    redact_secret_like_values: bool
    redaction_labels: tuple[str, ...]
    ci_log_policy: str


@dataclass(frozen=True)
class ErrorReportingPolicy:
    """Human escalation payload for collection failures."""

    notify_human: bool
    required_fields: tuple[str, ...]
    suppressed_fields: tuple[str, ...]


@dataclass(frozen=True)
class RepositoryConfig:
    """Validated repository collection configuration."""

    schema_version: int
    repository_id: str
    owner: str
    name: str
    url: str
    default_branch: str
    history_window: HistoryWindow
    artifact_scopes: tuple[ArtifactScope, ...]
    exclusion_rules: tuple[ExclusionRule, ...]
    private_info_policy: PrivateInfoPolicy
    error_reporting: ErrorReportingPolicy

    @property
    def enabled_artifact_kinds(self) -> tuple[ArtifactKind, ...]:
        return tuple(scope.kind for scope in self.artifact_scopes if scope.enabled)

    def artifact_scope(self, kind: ArtifactKind | str) -> ArtifactScope:
        artifact_kind = ArtifactKind(kind)
        for scope in self.artifact_scopes:
            if scope.kind == artifact_kind:
                return scope
        raise KeyError(f"artifact scope is not configured: {artifact_kind.value}")


def load_builtin_repository_config(repository_id: str = "react/react") -> RepositoryConfig:
    """Load a bundled repository configuration by repository ID."""

    resource_names = {
        "react/react": "react_react.json",
    }
    try:
        resource_name = resource_names[repository_id]
    except KeyError as exc:
        raise KeyError(f"unknown built-in repository config: {repository_id}") from exc

    config_resource = resources.files("git_archaeologist").joinpath(
        "config", "repositories", resource_name
    )
    return parse_repository_config(
        json.loads(config_resource.read_text(encoding="utf-8"))
    )


def load_repository_config(path: str | Path) -> RepositoryConfig:
    """Load a repository configuration from a JSON file."""

    config_path = Path(path)
    return parse_repository_config(
        json.loads(config_path.read_text(encoding="utf-8"))
    )


def parse_repository_config(raw_config: Mapping[str, Any]) -> RepositoryConfig:
    """Parse and validate a repository configuration mapping."""

    schema_version = _require_int(raw_config, "schema_version")
    if schema_version != 1:
        raise ValueError(f"unsupported repository config schema_version: {schema_version}")

    repository = _require_mapping(raw_config, "repository")
    repository_id = _require_str(repository, "id")
    owner = _require_str(repository, "owner")
    name = _require_str(repository, "name")
    url = _require_str(repository, "url")
    default_branch = _require_str(repository, "default_branch")
    history_window = _parse_history_window(_require_mapping(repository, "history"))

    _validate_repository_identity(repository_id, owner, name, url)
    if not default_branch.strip():
        raise ValueError("repository.default_branch must not be empty")

    artifact_scopes = tuple(
        _parse_artifact_scope(item)
        for item in _require_list(raw_config, "artifact_scopes")
    )
    _validate_artifact_scopes(artifact_scopes)

    exclusion_rules = tuple(
        _parse_exclusion_rule(item)
        for item in _require_list(raw_config, "exclusion_rules")
    )
    if not exclusion_rules:
        raise ValueError("exclusion_rules must contain at least one rule")

    private_info_policy = _parse_private_info_policy(
        _require_mapping(raw_config, "private_info_policy")
    )
    error_reporting = _parse_error_reporting_policy(
        _require_mapping(raw_config, "error_reporting")
    )
    _validate_error_reporting(error_reporting)

    return RepositoryConfig(
        schema_version=schema_version,
        repository_id=repository_id,
        owner=owner,
        name=name,
        url=url,
        default_branch=default_branch,
        history_window=history_window,
        artifact_scopes=artifact_scopes,
        exclusion_rules=exclusion_rules,
        private_info_policy=private_info_policy,
        error_reporting=error_reporting,
    )


def _parse_history_window(raw_history: Mapping[str, Any]) -> HistoryWindow:
    return HistoryWindow(
        since=_parse_datetime(_require_str(raw_history, "since"), "history.since"),
        until=_parse_datetime(_require_str(raw_history, "until"), "history.until"),
    )


def _parse_artifact_scope(raw_scope: Mapping[str, Any]) -> ArtifactScope:
    kind = ArtifactKind(_require_str(raw_scope, "kind"))
    enabled = _require_bool(raw_scope, "enabled")
    selectors = _optional_mapping(raw_scope, "selectors")
    history_window = None
    if "history" in raw_scope:
        history_window = _parse_history_window(_require_mapping(raw_scope, "history"))

    return ArtifactScope(
        kind=kind,
        enabled=enabled,
        selectors=MappingProxyType(dict(selectors)),
        history_window=history_window,
    )


def _parse_exclusion_rule(raw_rule: Mapping[str, Any]) -> ExclusionRule:
    return ExclusionRule(
        rule_id=_require_str(raw_rule, "id"),
        artifact_kinds=tuple(
            ArtifactKind(value)
            for value in _require_str_list(raw_rule, "artifact_kinds")
        ),
        field=_require_str(raw_rule, "field"),
        pattern=_require_str(raw_rule, "pattern"),
        reason=_require_str(raw_rule, "reason"),
    )


def _parse_private_info_policy(raw_policy: Mapping[str, Any]) -> PrivateInfoPolicy:
    return PrivateInfoPolicy(
        repository_visibility=_require_str(raw_policy, "repository_visibility"),
        allow_private_repository=_require_bool(raw_policy, "allow_private_repository"),
        store_raw_private_data=_require_bool(raw_policy, "store_raw_private_data"),
        redact_secret_like_values=_require_bool(
            raw_policy, "redact_secret_like_values"
        ),
        redaction_labels=tuple(_require_str_list(raw_policy, "redaction_labels")),
        ci_log_policy=_require_str(raw_policy, "ci_log_policy"),
    )


def _parse_error_reporting_policy(
    raw_policy: Mapping[str, Any],
) -> ErrorReportingPolicy:
    return ErrorReportingPolicy(
        notify_human=_require_bool(raw_policy, "notify_human"),
        required_fields=tuple(_require_str_list(raw_policy, "required_fields")),
        suppressed_fields=tuple(_require_str_list(raw_policy, "suppressed_fields")),
    )


def _validate_repository_identity(
    repository_id: str, owner: str, name: str, url: str
) -> None:
    expected_id = f"{owner}/{name}"
    if repository_id != expected_id:
        raise ValueError(
            f"repository.id must match owner/name: {repository_id!r} != {expected_id!r}"
        )

    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or parsed_url.netloc != "github.com":
        raise ValueError("repository.url must be an https://github.com URL")

    normalized_path = parsed_url.path.strip("/")
    if normalized_path != expected_id:
        raise ValueError(
            "repository.url path must match owner/name: "
            f"{normalized_path!r} != {expected_id!r}"
        )


def _validate_artifact_scopes(scopes: tuple[ArtifactScope, ...]) -> None:
    if not scopes:
        raise ValueError("artifact_scopes must contain at least one scope")

    seen_kinds: set[ArtifactKind] = set()
    for scope in scopes:
        if scope.kind in seen_kinds:
            raise ValueError(f"duplicate artifact scope: {scope.kind.value}")
        seen_kinds.add(scope.kind)

    enabled = {scope.kind for scope in scopes if scope.enabled}
    required = {ArtifactKind.PULL_REQUEST, ArtifactKind.ISSUE, ArtifactKind.CI_RUN}
    missing = required - enabled
    if missing:
        missing_values = ", ".join(sorted(kind.value for kind in missing))
        raise ValueError(f"required artifact scopes are not enabled: {missing_values}")


def _validate_error_reporting(policy: ErrorReportingPolicy) -> None:
    if not policy.notify_human:
        raise ValueError("error_reporting.notify_human must be true")

    required_fields = set(policy.required_fields)
    expected_fields = {
        "repository_id",
        "artifact_kind",
        "target",
        "operation",
        "error_type",
        "error_message",
    }
    missing = expected_fields - required_fields
    if missing:
        missing_values = ", ".join(sorted(missing))
        raise ValueError(
            "error_reporting.required_fields is missing required values: "
            f"{missing_values}"
        )


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 datetime") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _require_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = _require(raw, key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _optional_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _require_list(raw: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = _require(raw, key)
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{key} must be a list of objects")
    return value


def _require_str_list(raw: Mapping[str, Any], key: str) -> list[str]:
    value = _require(raw, key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"{key} must be a list of strings")
    return value


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = _require(raw, key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    value = _require(raw, key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _require_bool(raw: Mapping[str, Any], key: str) -> bool:
    value = _require(raw, key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _require(raw: Mapping[str, Any], key: str) -> Any:
    if key not in raw:
        raise ValueError(f"missing required field: {key}")
    return raw[key]
