"""Failure classification and safe fallback decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureKind(StrEnum):
    """External and model failure buckets that affect answer safety."""

    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    PARTIAL_FETCH = "partial_fetch"
    MODEL_STOPPED = "model_stopped"
    CONTEXT_OVERFLOW = "context_overflow"
    CORRUPT_INDEX = "corrupt_index"
    AUTH_OR_PERMISSION = "auth_or_permission"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FallbackDecision:
    """How the chat layer should respond to a failure."""

    failure_kind: FailureKind
    retryable: bool
    can_use_partial_evidence: bool
    user_message: str


def classify_failure_message(message: str) -> FailureKind:
    lowered = message.lower()
    if "rate limit" in lowered or "429" in lowered:
        return FailureKind.RATE_LIMIT
    if "timeout" in lowered or "timed out" in lowered:
        return FailureKind.TIMEOUT
    if "partial" in lowered or "incomplete" in lowered:
        return FailureKind.PARTIAL_FETCH
    if "context" in lowered and ("overflow" in lowered or "length" in lowered):
        return FailureKind.CONTEXT_OVERFLOW
    if "model" in lowered and ("stopped" in lowered or "unavailable" in lowered):
        return FailureKind.MODEL_STOPPED
    if "index" in lowered and ("corrupt" in lowered or "checksum" in lowered):
        return FailureKind.CORRUPT_INDEX
    if "permission" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
        return FailureKind.AUTH_OR_PERMISSION
    return FailureKind.UNKNOWN


def decide_fallback(failure_kind: FailureKind) -> FallbackDecision:
    """Return a safe, user-facing fallback policy for a known failure."""

    messages = {
        FailureKind.TIMEOUT: "取得または生成がtimeoutしました。再試行可能ですが、未取得部分を根拠として断言しません。",
        FailureKind.RATE_LIMIT: "GitHub APIのRate Limitに到達しました。解除後に再試行し、古い情報だけで断言しません。",
        FailureKind.PARTIAL_FETCH: "一部の履歴だけ取得できました。回答する場合は利用できた根拠の範囲を明示します。",
        FailureKind.MODEL_STOPPED: "モデル応答が途中で停止しました。途中回答は表示せず再生成を促します。",
        FailureKind.CONTEXT_OVERFLOW: "Evidence Packがcontext上限を超えました。根拠を絞り直すまで回答を生成しません。",
        FailureKind.CORRUPT_INDEX: "索引の整合性に問題があります。再構築するまで回答を停止します。",
        FailureKind.AUTH_OR_PERMISSION: "認証または権限不足で履歴を取得できません。権限確認後に再実行してください。",
        FailureKind.UNKNOWN: "予期しない失敗が発生しました。原因をtraceへ記録し、安全のため断言を避けます。",
    }
    return FallbackDecision(
        failure_kind=failure_kind,
        retryable=failure_kind
        in {
            FailureKind.TIMEOUT,
            FailureKind.RATE_LIMIT,
            FailureKind.MODEL_STOPPED,
            FailureKind.UNKNOWN,
        },
        can_use_partial_evidence=failure_kind is FailureKind.PARTIAL_FETCH,
        user_message=messages[failure_kind],
    )
