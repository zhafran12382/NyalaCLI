from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol

from core.reasoning import EffortMapping


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        status_code: int | None = None,
        reason: str = "",
        detail: str = "",
        endpoint: str = "",
        response_body: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.reason = reason
        self.detail = detail
        self.endpoint = endpoint
        self.response_body = response_body

    def summary(self) -> str:
        lines = ["Provider error"]
        if self.provider:
            lines.append(f"provider: {self.provider}")
        if self.status_code is not None:
            lines.append(f"code: {self.status_code}")
        if self.reason:
            lines.append(f"reason: {self.reason}")
        lines.append(f"message: {self.message}")
        if self.detail and self.detail != self.message:
            lines.append(f"detail: {self.detail}")
        return "\n".join(lines)

    def full_report(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status_code": self.status_code,
            "reason": self.reason,
            "message": self.message,
            "detail": self.detail,
            "endpoint": self.endpoint,
            "response_body": self.response_body,
        }


@dataclass
class ProviderResponse:
    content: str
    raw: dict[str, Any] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


class BaseProvider(Protocol):
    name: str

    def chat(self, messages: list[dict[str, str]]) -> ProviderResponse:
        ...


def normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        if role not in {"system", "user", "assistant", "tool"}:
            role = "user"
        normalized.append({"role": role, "content": str(message.get("content", ""))})
    return normalized


def iter_sse_json(response: Any) -> Iterator[dict[str, Any]]:
    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = str(raw_line).strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        elif line.startswith("event:"):
            continue
        if not line or line == "[DONE]":
            if line == "[DONE]":
                break
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            yield data


def collect_openai_stream(response: Any, on_delta: Callable[[str], None]) -> ProviderResponse:
    parts: list[str] = []
    usage: dict[str, Any] = {}
    event_count = 0
    for data in iter_sse_json(response):
        event_count += 1
        if isinstance(data.get("usage"), dict):
            usage = data["usage"]
        choices = data.get("choices") or []
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                continue
            content = delta.get("content")
            if content:
                text = str(content)
                parts.append(text)
                on_delta(text)
    return ProviderResponse(
        content="".join(parts),
        raw={"stream": True, "events": event_count},
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )


def provider_error_from_response(name: str, response: Any, endpoint: str = "") -> ProviderError:
    response_body = str(getattr(response, "text", "") or "")
    try:
        data = response.json()
    except ValueError:
        data = {}
    detail = ""
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or error.get("detail") or error)
        else:
            detail = str(data.get("message") or data.get("detail") or response_body)
    else:
        detail = response_body
    status_code = int(getattr(response, "status_code", 0) or 0)
    reason = str(getattr(response, "reason", "") or _reason_from_status(status_code))
    message = _message_from_status(name, status_code, detail)
    return ProviderError(
        message,
        provider=name,
        status_code=status_code,
        reason=reason,
        detail=detail[:2000],
        endpoint=endpoint,
        response_body=response_body[:8000],
    )


def log_model_request(
    config: dict[str, Any],
    *,
    provider: str,
    model: str,
    endpoint: str,
    payload: dict[str, Any],
    effort_mapping: EffortMapping | None,
) -> None:
    if not effort_mapping and not config.get("debug"):
        return
    log_path = _request_log_path(config)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": config.get("_session_id", ""),
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "requested_effort": effort_mapping.requested_effort if effort_mapping else "",
        "provider_mapped_effort": effort_mapping.provider_effort if effort_mapping else "",
        "effort_field": effort_mapping.field_path if effort_mapping else "",
        "effort_payload": effort_mapping.payload_fragment if effort_mapping else {},
        "effort_note": effort_mapping.note if effort_mapping else "",
        "payload_keys": sorted(payload.keys()),
        "message_count": len(payload.get("messages") or payload.get("contents") or []),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def add_effort_error_hint(error: ProviderError, effort_mapping: EffortMapping | None) -> ProviderError:
    if not effort_mapping:
        return error
    hint = (
        f"Effort sent: requested={effort_mapping.requested_effort}, "
        f"mapped={effort_mapping.provider_effort}, field={effort_mapping.field_path}. "
        "Gunakan /effort off atau pilih model/provider yang mendukung jika backend menolak parameter ini."
    )
    error.detail = f"{error.detail}\n{hint}".strip()
    error.message = f"{error.message}\n{hint}"
    return error


def _request_log_path(config: dict[str, Any]) -> Path:
    configured = str(config.get("_request_log_path") or "").strip()
    if configured:
        return Path(configured)
    return Path.home() / ".nyalacli" / "logs" / "model_requests.log"


def _message_from_status(name: str, status_code: int, detail: str) -> str:
    if status_code in {401, 403}:
        return f"{name}: API key ditolak atau tidak punya akses."
    if status_code == 404:
        return f"{name}: model/provider/endpoint tidak ditemukan."
    if status_code == 429:
        return f"{name}: quota/rate limit tercapai."
    if detail:
        return f"{name}: HTTP {status_code}. {detail[:300]}"
    return f"{name}: HTTP {status_code}."


def _reason_from_status(status_code: int) -> str:
    reasons = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        408: "Request Timeout",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }
    return reasons.get(status_code, "")
