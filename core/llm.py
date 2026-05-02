from __future__ import annotations

from typing import Any

from providers.gemini import GeminiProvider
from providers.openai_compatible import OpenAICompatibleProvider
from providers.openrouter import OpenRouterProvider

from .provider_catalog import OPENAI_COMPATIBLE_PROVIDERS, normalize_provider_name


def build_provider(config: dict[str, Any]):
    provider = normalize_provider_name(str(config.get("provider", "openrouter")))
    if provider == "openrouter":
        return OpenRouterProvider(config)
    if provider == "gemini":
        return GeminiProvider(config)
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        return OpenAICompatibleProvider(config)
    raise ValueError(f"Provider tidak dikenal: {provider}")
