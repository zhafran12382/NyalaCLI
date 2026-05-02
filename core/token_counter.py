from __future__ import annotations

from typing import Any


TOKEN_TARGET = 1_000_000


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4)) if text else 0


def estimate_messages(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        total += estimate_tokens(str(message.get("role", "")))
        total += estimate_tokens(str(message.get("content", "")))
    return total


def token_report(messages: list[dict[str, Any]], last_response_tokens: int = 0) -> dict[str, Any]:
    context_tokens = estimate_messages(messages)
    warning = ""
    if context_tokens > TOKEN_TARGET:
        warning = "Estimasi context melewati target 1M token. Jalankan /compact."
    elif context_tokens > int(TOKEN_TARGET * 0.8):
        warning = "Estimasi context mendekati 1M token."
    return {
        "total_messages": len(messages),
        "estimated_context_tokens": context_tokens,
        "target_tokens": TOKEN_TARGET,
        "estimated_last_response_tokens": last_response_tokens,
        "warning": warning,
    }
