"""CI failure retention, parsing, and stable signature generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import re


class RetentionMode(StrEnum):
    """Whether a CI log can be stored or must be summarized."""

    STORE_REDACTED_EXCERPT = "store_redacted_excerpt"
    SUMMARY_ONLY = "summary_only"
    REFETCH_REQUIRED = "refetch_required"


@dataclass(frozen=True)
class CIRetentionPolicy:
    """Rules for keeping CI failure evidence without storing credentials."""

    failed_jobs_only: bool = True
    max_excerpt_bytes: int = 8192
    retention_mode: RetentionMode = RetentionMode.STORE_REDACTED_EXCERPT
    redacted_markers: tuple[str, ...] = ("token", "authorization", "password", "secret", "private_key")


@dataclass(frozen=True)
class CIFailureEvent:
    """Searchable CI failure event extracted from a redacted log excerpt."""

    event_id: str
    repository_id: str
    workflow_name: str
    job_name: str
    step_name: str
    test_name: str | None
    error_class: str
    message: str
    stack_frames: tuple[str, ...]
    head_sha: str
    occurred_at: str
    source_url: str
    redacted_excerpt: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FailureSignature:
    """Stable key for grouping recurring CI failures."""

    signature_id: str
    test_name: str | None
    error_class: str
    normalized_message: str
    primary_stack_frame: str | None
    components: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_SECRET_LINE_RE = re.compile(
    r"(?i)(authorization|token|password|secret|private[_-]?key)\s*[:=]\s*([^\s]+)"
)
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+\b")
_PATH_LINE_RE = re.compile(r"(?P<path>[\w./\\-]+\.(?:js|jsx|ts|tsx|py)):(?P<line>\d+)")
_ERROR_RE = re.compile(r"(?P<class>[A-Za-z_][\w.]*(?:Error|Exception|Failure))[:\s]+(?P<message>.+)")


def redact_ci_log(log_text: str, policy: CIRetentionPolicy | None = None) -> str:
    """Redact secrets and truncate CI logs according to the retention policy."""

    policy = policy or CIRetentionPolicy()
    redacted = _SECRET_LINE_RE.sub(lambda match: f"{match.group(1)}=<redacted>", log_text)
    encoded = redacted.encode("utf-8")
    if len(encoded) <= policy.max_excerpt_bytes:
        return redacted
    return encoded[: policy.max_excerpt_bytes].decode("utf-8", errors="ignore")


def parse_ci_failure_event(
    *,
    repository_id: str,
    workflow_name: str,
    job_name: str,
    step_name: str,
    head_sha: str,
    occurred_at: str,
    source_url: str,
    log_text: str,
    policy: CIRetentionPolicy | None = None,
) -> CIFailureEvent:
    """Build a structured CI failure event from a raw log excerpt."""

    redacted_excerpt = redact_ci_log(log_text, policy)
    error_class, message = _extract_error(redacted_excerpt)
    stack_frames = tuple(match.group(0).replace("\\", "/") for match in _PATH_LINE_RE.finditer(redacted_excerpt))
    test_name = _extract_test_name(redacted_excerpt)
    event_hash = hashlib.sha256(
        "|".join((repository_id, workflow_name, job_name, step_name, head_sha, error_class, message)).encode("utf-8")
    ).hexdigest()[:16]
    return CIFailureEvent(
        event_id=f"ci-failure-{event_hash}",
        repository_id=repository_id,
        workflow_name=workflow_name,
        job_name=job_name,
        step_name=step_name,
        test_name=test_name,
        error_class=error_class,
        message=message,
        stack_frames=stack_frames,
        head_sha=head_sha,
        occurred_at=occurred_at,
        source_url=source_url,
        redacted_excerpt=redacted_excerpt,
    )


def generate_failure_signature(event: CIFailureEvent) -> FailureSignature:
    """Generate a path/line/ID-stable signature for a CI failure."""

    normalized_message = _normalize_signature_text(event.message)
    primary_stack_frame = _normalize_stack_frame(event.stack_frames[0]) if event.stack_frames else None
    components = tuple(
        component
        for component in (event.test_name, event.error_class, normalized_message, primary_stack_frame)
        if component
    )
    signature_hash = hashlib.sha256("|".join(components).encode("utf-8")).hexdigest()[:16]
    return FailureSignature(
        signature_id=f"failure-signature-{signature_hash}",
        test_name=event.test_name,
        error_class=event.error_class,
        normalized_message=normalized_message,
        primary_stack_frame=primary_stack_frame,
        components=components,
    )


def _extract_error(log_text: str) -> tuple[str, str]:
    for line in log_text.splitlines():
        match = _ERROR_RE.search(line.strip())
        if match:
            return match.group("class"), match.group("message")
    for line in log_text.splitlines():
        if line.strip():
            return "CIError", line.strip()
    return "CIError", "unknown failure"


def _extract_test_name(log_text: str) -> str | None:
    for marker in ("FAIL ", "FAILED "):
        for line in log_text.splitlines():
            stripped = line.strip()
            if stripped.startswith(marker):
                return stripped[len(marker) :].split()[0]
    return None


def _normalize_signature_text(value: str) -> str:
    normalized = _SHA_RE.sub("<sha>", value.lower())
    normalized = _NUMBER_RE.sub("<num>", normalized)
    return " ".join(normalized.split())


def _normalize_stack_frame(value: str) -> str:
    normalized = value.replace("\\", "/")
    return re.sub(r":\d+", ":<line>", normalized)
