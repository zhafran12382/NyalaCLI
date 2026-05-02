from __future__ import annotations

import json
import os
from typing import Any, Callable

import requests

from core.reasoning import EffortUnsupportedError, apply_effort_to_payload

from .base import (
    ProviderError,
    ProviderResponse,
    add_effort_error_hint,
    collect_openai_stream,
    log_model_request,
    normalize_messages,
    provider_error_from_response,
)


class OpenRouterProvider:
    name = "openrouter"
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.model = config.get("model", "openrouter/free")
        self.temperature = float(config.get("temperature", 0.4))
        self.max_tokens = int(config.get("max_tokens", 2048))
        self.routing = str(config.get("routing", "")).strip()

    def chat(self, messages: list[dict[str, str]]) -> ProviderResponse:
        payload, headers, effort_mapping = self._request_parts(messages)
        log_model_request(
            self.config,
            provider="OpenRouter",
            model=self.model,
            endpoint=self.endpoint,
            payload=payload,
            effort_mapping=effort_mapping,
        )
        try:
            response = requests.post(self.endpoint, headers=headers, json=payload, timeout=90)
        except requests.RequestException as exc:
            raise ProviderError(
                f"Gagal menghubungi OpenRouter: {exc}",
                provider="OpenRouter",
                reason=exc.__class__.__name__,
                detail=str(exc),
                endpoint=self.endpoint,
            ) from exc
        if response.status_code >= 400:
            raise add_effort_error_hint(provider_error_from_response("OpenRouter", response, self.endpoint), effort_mapping)
        try:
            data = response.json()
            choice = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {}) or {}
        except (ValueError, KeyError, IndexError) as exc:
            raise ProviderError("Respons OpenRouter tidak valid.") from exc
        return ProviderResponse(
            content=str(choice or ""),
            raw=data,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )

    def chat_stream(self, messages: list[dict[str, str]], on_delta: Callable[[str], None]) -> ProviderResponse:
        payload, headers, effort_mapping = self._request_parts(messages)
        payload["stream"] = True
        log_model_request(
            self.config,
            provider="OpenRouter",
            model=self.model,
            endpoint=self.endpoint,
            payload=payload,
            effort_mapping=effort_mapping,
        )
        try:
            response = requests.post(self.endpoint, headers=headers, json=payload, timeout=90, stream=True)
        except requests.RequestException as exc:
            raise ProviderError(
                f"Gagal menghubungi OpenRouter: {exc}",
                provider="OpenRouter",
                reason=exc.__class__.__name__,
                detail=str(exc),
                endpoint=self.endpoint,
            ) from exc
        if response.status_code >= 400:
            raise add_effort_error_hint(provider_error_from_response("OpenRouter", response, self.endpoint), effort_mapping)
        return collect_openai_stream(response, on_delta)

    def _request_parts(self, messages: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, str], Any]:
        if not self.api_key:
            raise ProviderError("OPENROUTER_API_KEY belum dikonfigurasi. Jalankan `python main.py setup`.")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": normalize_messages(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        provider_routing = parse_openrouter_routing(self.routing)
        if provider_routing:
            payload["provider"] = provider_routing
        try:
            effort_mapping = apply_effort_to_payload(payload, self.config)
        except EffortUnsupportedError as exc:
            raise ProviderError(
                str(exc),
                provider="OpenRouter",
                reason="UnsupportedEffort",
                endpoint=self.endpoint,
            ) from exc
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://nyalacli.local",
            "X-Title": "NyalaCLI",
        }
        return payload, headers, effort_mapping


def parse_openrouter_routing(raw: str) -> dict[str, Any] | None:
    routing = raw.strip()
    if not routing or routing.lower() == "auto":
        return None
    if routing.startswith("{"):
        try:
            data = json.loads(routing)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Routing OpenRouter JSON tidak valid: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError("Routing OpenRouter JSON harus berupa object.")
        if isinstance(data.get("provider"), dict):
            data = data["provider"]
        return _normalize_provider_object(data)
    order = [item.strip().lower() for item in routing.split(",") if item.strip()]
    if not order:
        return None
    return {"order": order, "allow_fallbacks": True}


def _normalize_provider_object(data: dict[str, Any]) -> dict[str, Any]:
    key_aliases = {
        "allowFallbacks": "allow_fallbacks",
        "requireParameters": "require_parameters",
        "dataCollection": "data_collection",
        "maxPrice": "max_price",
        "enforceDistillableText": "enforce_distillable_text",
    }
    list_keys = {"order", "only", "ignore", "quantizations"}
    simple_keys = {
        "allow_fallbacks",
        "require_parameters",
        "zdr",
        "enforce_distillable_text",
        "data_collection",
        "sort",
        "max_price",
    }
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        normalized_key = key_aliases.get(str(key), str(key))
        if normalized_key in list_keys:
            normalized[normalized_key] = _as_list(value, normalized_key)
        elif normalized_key in simple_keys:
            normalized[normalized_key] = value
        else:
            normalized[normalized_key] = value
    if not normalized:
        return {}
    return normalized


def _as_list(value: Any, key: str) -> list[str]:
    if isinstance(value, str):
        return [item.strip().lower() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    raise ProviderError(f"Routing OpenRouter field `{key}` harus string koma atau list.")
