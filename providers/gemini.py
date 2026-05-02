from __future__ import annotations

import os
from typing import Any, Callable
from urllib.parse import quote

import requests

from core.reasoning import EffortUnsupportedError, apply_effort_to_payload

from .base import (
    ProviderError,
    ProviderResponse,
    add_effort_error_hint,
    log_model_request,
    iter_sse_json,
    provider_error_from_response,
)


class GeminiProvider:
    name = "gemini"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.model = config.get("model", "gemini-1.5-flash")
        self.temperature = float(config.get("temperature", 0.4))
        self.max_tokens = int(config.get("max_tokens", 2048))

    def chat(self, messages: list[dict[str, str]]) -> ProviderResponse:
        endpoint, payload, effort_mapping = self._request_parts(messages, stream=False)
        log_model_request(
            self.config,
            provider="Gemini",
            model=self.model,
            endpoint=_redact_key(endpoint),
            payload=payload,
            effort_mapping=effort_mapping,
        )
        try:
            response = requests.post(endpoint, json=payload, timeout=90)
        except requests.RequestException as exc:
            raise ProviderError(
                f"Gagal menghubungi Gemini: {exc}",
                provider="Gemini",
                reason=exc.__class__.__name__,
                detail=str(exc),
                endpoint=_redact_key(endpoint),
            ) from exc
        if response.status_code >= 400:
            raise add_effort_error_hint(provider_error_from_response("Gemini", response, _redact_key(endpoint)), effort_mapping)
        try:
            data = response.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
            usage = data.get("usageMetadata", {}) or {}
        except (ValueError, KeyError, IndexError) as exc:
            raise ProviderError("Respons Gemini tidak valid.") from exc
        return ProviderResponse(
            content=text,
            raw=data,
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            completion_tokens=int(usage.get("candidatesTokenCount") or 0),
        )

    def chat_stream(self, messages: list[dict[str, str]], on_delta: Callable[[str], None]) -> ProviderResponse:
        endpoint, payload, effort_mapping = self._request_parts(messages, stream=True)
        log_model_request(
            self.config,
            provider="Gemini",
            model=self.model,
            endpoint=_redact_key(endpoint),
            payload=payload,
            effort_mapping=effort_mapping,
        )
        try:
            response = requests.post(endpoint, json=payload, timeout=90, stream=True)
        except requests.RequestException as exc:
            raise ProviderError(
                f"Gagal menghubungi Gemini: {exc}",
                provider="Gemini",
                reason=exc.__class__.__name__,
                detail=str(exc),
                endpoint=_redact_key(endpoint),
            ) from exc
        if response.status_code >= 400:
            raise add_effort_error_hint(provider_error_from_response("Gemini", response, _redact_key(endpoint)), effort_mapping)
        parts: list[str] = []
        usage: dict[str, Any] = {}
        events = 0
        for data in iter_sse_json(response):
            events += 1
            if isinstance(data.get("usageMetadata"), dict):
                usage = data["usageMetadata"]
            for candidate in data.get("candidates", []) or []:
                content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
                for part in content.get("parts", []) or []:
                    text = str(part.get("text", "") if isinstance(part, dict) else "")
                    if text:
                        parts.append(text)
                        on_delta(text)
        return ProviderResponse(
            content="".join(parts),
            raw={"stream": True, "events": events},
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            completion_tokens=int(usage.get("candidatesTokenCount") or 0),
        )

    def _request_parts(self, messages: list[dict[str, str]], stream: bool) -> tuple[str, dict[str, Any], Any]:
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY belum dikonfigurasi. Jalankan `python main.py setup`.")
        model = quote(self.model, safe="")
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:{'streamGenerateContent?alt=sse&' if stream else 'generateContent?'}key={self.api_key}"
        )
        system_text = ""
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            text = str(message.get("content", ""))
            if role == "system":
                system_text += text + "\n"
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": text}]})
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }
        if system_text.strip():
            payload["systemInstruction"] = {"parts": [{"text": system_text.strip()}]}
        try:
            effort_mapping = apply_effort_to_payload(payload, self.config)
        except EffortUnsupportedError as exc:
            raise ProviderError(
                str(exc),
                provider="Gemini",
                reason="UnsupportedEffort",
                endpoint=_redact_key(endpoint),
            ) from exc
        return endpoint, payload, effort_mapping

def _redact_key(endpoint: str) -> str:
    return endpoint.split("?key=", 1)[0] + "?key=<redacted>" if "?key=" in endpoint else endpoint
