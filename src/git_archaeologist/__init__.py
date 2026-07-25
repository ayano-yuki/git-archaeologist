"""Git Archaeologist package."""

from git_archaeologist.gh_access import (
    GhCheckKind,
    GhCheckResult,
    GhCommandResult,
    GhErrorType,
    GhFailure,
    GhPreflightReport,
    check_github_access,
    classify_gh_error,
    run_gh_command,
)
from git_archaeologist.repository_config import (
    ArtifactKind,
    ArtifactScope,
    ErrorReportingPolicy,
    ExclusionRule,
    HistoryWindow,
    PrivateInfoPolicy,
    RepositoryConfig,
    load_builtin_repository_config,
    load_repository_config,
    parse_repository_config,
)

__all__ = [
    "GhCheckKind",
    "GhCheckResult",
    "GhCommandResult",
    "GhErrorType",
    "GhFailure",
    "GhPreflightReport",
    "check_github_access",
    "classify_gh_error",
    "run_gh_command",
    "ArtifactKind",
    "ArtifactScope",
    "ErrorReportingPolicy",
    "ExclusionRule",
    "HistoryWindow",
    "PrivateInfoPolicy",
    "RepositoryConfig",
    "load_builtin_repository_config",
    "load_repository_config",
    "parse_repository_config",
]

