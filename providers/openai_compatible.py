from __future__ import annotations

import os
from typing import Any, Callable

import requests

from core.provider_catalog import get_provider_option, normalize_provider_name
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


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.provider = normalize_provider_name(str(config.get("provider", "openai_compatible")))
        self.option = get_provider_option(self.provider)
        self.name = self.provider
        env_key = self.option.api_key_env or "OPENAI_API_KEY"
        self.api_key = os.environ.get(env_key, "")
        if self.option.editable_base_url:
            base_url = config.get("base_url") or self.option.base_url
        else:
            base_url = self.option.base_url
        self.base_url = str(base_url).rstrip("/")
        self.model = config.get("model") or self.option.default_model
        self.temperature = float(config.get("temperature", 0.4))
        self.max_tokens = int(config.get("max_tokens", 2048))

    def chat(self, messages: list[dict[str, str]]) -> ProviderResponse:
        payload, headers, endpoint, effort_mapping = self._request_parts(messages)
        log_model_request(
            self.config,
            provider=self._display_name(),
            model=self.model,
            endpoint=endpoint,
            payload=payload,
            effort_mapping=effort_mapping,
        )
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=90,
            )
        except requests.RequestException as exc:
            raise ProviderError(
                f"Gagal menghubungi endpoint {self._display_name()}: {exc}",
                provider=self._display_name(),
                reason=exc.__class__.__name__,
                detail=str(exc),
                endpoint=endpoint,
            ) from exc
        if response.status_code >= 400:
            raise add_effort_error_hint(provider_error_from_response(self._display_name(), response, endpoint), effort_mapping)
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {}) or {}
        except (ValueError, KeyError, IndexError) as exc:
            raise ProviderError("Respons OpenAI-compatible tidak valid.") from exc
        return ProviderResponse(
            content=str(content or ""),
            raw=data,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )

    def chat_stream(self, messages: list[dict[str, str]], on_delta: Callable[[str], None]) -> ProviderResponse:
        payload, headers, endpoint, effort_mapping = self._request_parts(messages)
        payload["stream"] = True
        log_model_request(
            self.config,
            provider=self._display_name(),
            model=self.model,
            endpoint=endpoint,
            payload=payload,
            effort_mapping=effort_mapping,
        )
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=90,
                stream=True,
            )
        except requests.RequestException as exc:
            raise ProviderError(
                f"Gagal menghubungi endpoint {self._display_name()}: {exc}",
                provider=self._display_name(),
                reason=exc.__class__.__name__,
                detail=str(exc),
                endpoint=endpoint,
            ) from exc
        if response.status_code >= 400:
            raise add_effort_error_hint(provider_error_from_response(self._display_name(), response, endpoint), effort_mapping)
        return collect_openai_stream(response, on_delta)

    def _request_parts(self, messages: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, str], str, Any]:
        if not self.api_key and not self.option.api_key_optional:
            raise ProviderError(f"{self._display_name()}: API key belum dikonfigurasi.")
        if not self.base_url:
            raise ProviderError(f"{self._display_name()}: base_url belum dikonfigurasi.")
        payload = {
            "model": self.model,
            "messages": normalize_messages(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        try:
            effort_mapping = apply_effort_to_payload(payload, self.config)
        except EffortUnsupportedError as exc:
            raise ProviderError(
                str(exc),
                provider=self._display_name(),
                reason="UnsupportedEffort",
                endpoint=f"{self.base_url}/chat/completions",
            ) from exc
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        endpoint = f"{self.base_url}/chat/completions"
        return payload, headers, endpoint, effort_mapping

    def _display_name(self) -> str:
        if self.provider == "custom":
            return str(self.config.get("custom_provider_name") or self.option.label)
        return self.option.label
