from __future__ import annotations

from typing import Any

VALID_ROLES = {"system", "user", "assistant", "tool"}


def validate_messages_record(record: dict[str, Any]) -> list[str]:
    """Return validation errors for one chat-style SFT record."""
    errors: list[str] = []
    messages = record.get("messages")

    if not isinstance(messages, list) or not messages:
        return ["record must contain a non-empty messages list"]

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            errors.append(f"messages[{index}] must be an object")
            continue

        role = message.get("role")
        content = message.get("content")

        if role not in VALID_ROLES:
            errors.append(f"messages[{index}].role must be one of {sorted(VALID_ROLES)}")
        if not isinstance(content, str) or not content.strip():
            errors.append(f"messages[{index}].content must be a non-empty string")

    if not any(message.get("role") == "user" for message in messages if isinstance(message, dict)):
        errors.append("record must contain at least one user message")
    if not any(message.get("role") == "assistant" for message in messages if isinstance(message, dict)):
        errors.append("record must contain at least one assistant message")

    return errors
