from __future__ import annotations

import json
from typing import Any

import pytest

from core.reasoning import EffortUnsupportedError, apply_effort_to_payload, provider_effort_mapping
from providers.gemini import GeminiProvider
from providers.openai_compatible import OpenAICompatibleProvider
from providers.openrouter import OpenRouterProvider


class FakeResponse:
    status_code = 200
    reason = "OK"
    text = "{}"

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.text = json.dumps(data)

    def json(self) -> dict[str, Any]:
        return self._data


def chat_response(content: str = "ok") -> FakeResponse:
    return FakeResponse({"choices": [{"message": {"content": content}}], "usage": {}})


def gemini_response(content: str = "ok") -> FakeResponse:
    return FakeResponse({"candidates": [{"content": {"parts": [{"text": content}]}}], "usageMetadata": {}})


def test_openrouter_effort_reaches_outbound_payload(monkeypatch, tmp_path) -> None:
    captured: dict[str, Any] = {}

    def post(_endpoint, headers=None, json=None, timeout=None):
        captured["headers"] = headers
        captured["payload"] = json
        return chat_response()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr("providers.openrouter.requests.post", post)
    provider = OpenRouterProvider(
        {
            "provider": "openrouter",
            "model": "openai/gpt-5-mini",
            "thinking_effort": "xhigh",
            "_request_log_path": str(tmp_path / "model_requests.log"),
        }
    )

    provider.chat([{"role": "user", "content": "hello"}])

    assert captured["payload"]["reasoning"] == {"effort": "xhigh", "exclude": True}
    log = (tmp_path / "model_requests.log").read_text(encoding="utf-8")
    assert '"requested_effort": "xhigh"' in log
    assert '"provider_mapped_effort": "xhigh"' in log
    assert '"effort_field": "reasoning.effort"' in log


def test_openai_effort_reaches_outbound_payload(monkeypatch, tmp_path) -> None:
    captured: dict[str, Any] = {}

    def post(_endpoint, headers=None, json=None, timeout=None):
        captured["payload"] = json
        return chat_response()

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr("providers.openai_compatible.requests.post", post)
    provider = OpenAICompatibleProvider(
        {
            "provider": "openai",
            "model": "gpt-5.4",
            "thinking_effort": "high",
            "_request_log_path": str(tmp_path / "model_requests.log"),
        }
    )

    provider.chat([{"role": "user", "content": "hello"}])

    assert captured["payload"]["reasoning_effort"] == "high"
    assert '"effort_field": "reasoning_effort"' in (tmp_path / "model_requests.log").read_text(encoding="utf-8")


def test_gemini_xhigh_maps_to_supported_thinking_level(monkeypatch, tmp_path) -> None:
    captured: dict[str, Any] = {}

    def post(_endpoint, json=None, timeout=None):
        captured["payload"] = json
        return gemini_response()

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr("providers.gemini.requests.post", post)
    provider = GeminiProvider(
        {
            "provider": "gemini",
            "model": "gemini-3-flash-preview",
            "thinking_effort": "xhigh",
            "_request_log_path": str(tmp_path / "model_requests.log"),
        }
    )

    provider.chat([{"role": "user", "content": "hello"}])

    thinking = captured["payload"]["generationConfig"]["thinkingConfig"]
    assert thinking == {"thinkingLevel": "high"}
    log = (tmp_path / "model_requests.log").read_text(encoding="utf-8")
    assert '"requested_effort": "xhigh"' in log
    assert '"provider_mapped_effort": "high"' in log


def test_unsupported_provider_effort_is_rejected() -> None:
    payload: dict[str, Any] = {"messages": []}

    with pytest.raises(EffortUnsupportedError):
        apply_effort_to_payload(payload, {"provider": "groq", "model": "llama-3.1-8b-instant", "thinking_effort": "high"})


def test_gemini_25_effort_maps_to_thinking_budget() -> None:
    mapping = provider_effort_mapping({"provider": "gemini", "model": "gemini-2.5-flash"}, "medium")

    assert mapping.field_path == "generationConfig.thinkingConfig.thinkingBudget"
    assert mapping.payload_fragment["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 4096
