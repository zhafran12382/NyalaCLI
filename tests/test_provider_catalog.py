from __future__ import annotations

from core.llm import build_provider
from core.provider_catalog import get_provider_option, normalize_provider_name
from main import _model_is_allowed_by_price, _model_is_text_or_multimodal_chat
from providers.base import provider_error_from_response
from providers.openai_compatible import OpenAICompatibleProvider
from providers.openrouter import parse_openrouter_routing


def test_provider_aliases_normalize() -> None:
    assert normalize_provider_name("local") == "openai_compatible"
    assert normalize_provider_name("custom-openai-compatible") == "custom"


def test_build_provider_supports_openai_compatible_catalog() -> None:
    provider = build_provider({"provider": "groq", "model": "llama-3.1-8b-instant"})
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == get_provider_option("groq").base_url


def test_editable_openai_compatible_uses_config_base_url() -> None:
    provider = build_provider(
        {
            "provider": "custom",
            "model": "test-model",
            "base_url": "https://example.test/v1",
        }
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://example.test/v1"


def test_openrouter_routing_auto_is_empty() -> None:
    assert parse_openrouter_routing("") is None
    assert parse_openrouter_routing("auto") is None


def test_openrouter_routing_comma_list() -> None:
    assert parse_openrouter_routing("DeepInfra,Together") == {
        "order": ["deepinfra", "together"],
        "allow_fallbacks": True,
    }


def test_openrouter_routing_json_object() -> None:
    assert parse_openrouter_routing('{"order":["DeepInfra"],"allowFallbacks":false}') == {
        "order": ["deepinfra"],
        "allow_fallbacks": False,
    }


def test_model_filter_requires_text_output() -> None:
    model = {
        "id": "music/lyra",
        "name": "Lyra Music",
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["audio"],
        },
    }
    assert _model_is_text_or_multimodal_chat(model) is False


def test_model_filter_allows_multimodal_text_output() -> None:
    model = {
        "id": "google/gemini-2.5-flash",
        "name": "Google: Gemini 2.5 Flash",
        "architecture": {
            "input_modalities": ["text", "image", "audio"],
            "output_modalities": ["text"],
        },
    }
    assert _model_is_text_or_multimodal_chat(model) is True


def test_model_price_filter_uses_blended_price() -> None:
    model = {
        "id": "cheap/model",
        "pricing": {"prompt": "0.000003", "completion": "0.000007"},
    }
    assert _model_is_allowed_by_price(model) is True


def test_provider_error_summary_includes_status_detail() -> None:
    class Response:
        status_code = 429
        reason = "Too Many Requests"
        text = '{"error":{"message":"quota exceeded"}}'

        def json(self):
            return {"error": {"message": "quota exceeded"}}

    error = provider_error_from_response("OpenRouter", Response(), "https://example.test")
    summary = error.summary()
    assert "code: 429" in summary
    assert "quota exceeded" in summary
