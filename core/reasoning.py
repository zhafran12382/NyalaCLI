from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import requests

from .provider_catalog import normalize_provider_name


EFFORT_LEVELS = ("minimal", "low", "medium", "high", "xhigh")
EFFORT_LABELS = {
    "minimal": "Minimal",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "Xhigh",
}
EFFORT_OFF_VALUES = {"", "off", "none", "disable", "disabled", "mati"}
REASONING_PARAMETERS = {"reasoning", "include_reasoning", "reasoning_effort"}
GEMINI_25_BUDGETS = {
    "minimal": 512,
    "low": 1024,
    "medium": 4096,
    "high": 8192,
    "xhigh": 16384,
}


class EffortUnsupportedError(ValueError):
    pass


@dataclass(frozen=True)
class EffortMapping:
    requested_effort: str
    provider_effort: str
    field_path: str
    payload_fragment: dict[str, Any]
    note: str = ""


def normalize_effort(value: str) -> str:
    effort = value.strip().lower()
    if effort in EFFORT_OFF_VALUES:
        return ""
    if effort not in EFFORT_LEVELS:
        valid = ", ".join(label for label in EFFORT_LABELS.values())
        raise ValueError(f"Effort valid: {valid}, atau off")
    return effort


def effort_display(value: str | None) -> str:
    effort = (value or "").strip().lower()
    return EFFORT_LABELS.get(effort, "Off")


def configured_effort(config: dict[str, Any]) -> str:
    raw = str(config.get("thinking_effort") or "").strip()
    return normalize_effort(raw) if raw else ""


def apply_effort_to_payload(payload: dict[str, Any], config: dict[str, Any]) -> EffortMapping | None:
    effort = configured_effort(config)
    if not effort:
        return None
    mapping = provider_effort_mapping(config, effort)
    _deep_merge(payload, mapping.payload_fragment)
    return mapping


def provider_effort_mapping(config: dict[str, Any], effort: str | None = None) -> EffortMapping:
    requested = normalize_effort(effort if effort is not None else configured_effort(config))
    if not requested:
        raise EffortUnsupportedError("Effort tidak aktif.")
    provider = normalize_provider_name(str(config.get("provider", "openrouter")))
    model = str(config.get("model", "")).strip()

    if provider == "openrouter":
        if model in {"openrouter/free", "openrouter/auto"}:
            raise EffortUnsupportedError(
                "Model router otomatis OpenRouter tidak punya capability reasoning yang pasti. "
                "Pilih model spesifik yang mendukung reasoning."
            )
        return EffortMapping(
            requested_effort=requested,
            provider_effort=requested,
            field_path="reasoning.effort",
            payload_fragment={"reasoning": {"effort": requested, "exclude": True}},
        )

    if provider == "gemini":
        return _gemini_effort_mapping(model, requested)

    if provider == "openai":
        if not _is_openai_reasoning_model(model):
            raise EffortUnsupportedError(
                f"Model OpenAI `{model}` tidak tampak sebagai reasoning model. "
                "Gunakan model GPT-5/o-series atau matikan dengan /effort off."
            )
        return EffortMapping(
            requested_effort=requested,
            provider_effort=requested,
            field_path="reasoning_effort",
            payload_fragment={"reasoning_effort": requested},
        )

    raise EffortUnsupportedError(
        f"Provider `{provider}` belum punya adapter effort. "
        "Gunakan OpenRouter, Gemini thinking model, OpenAI reasoning model, atau /effort off."
    )


def model_supports_thinking(config: dict[str, Any]) -> tuple[bool, str]:
    provider = normalize_provider_name(str(config.get("provider", "openrouter")))
    model = str(config.get("model", "")).strip()
    if provider == "openrouter":
        if model in {"openrouter/free", "openrouter/auto"}:
            return False, "Model router otomatis tidak punya capability thinking yang pasti. Pilih model spesifik yang mendukung reasoning."
        try:
            metadata = _openrouter_model_metadata(model)
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            fallback = _fallback_thinking_support(model)
            if fallback:
                return True, (
                    f"Gagal cek metadata OpenRouter: {exc}. "
                    "Effort diizinkan berdasarkan pola model id; backend akan menolak jika model ternyata tidak mendukung."
                )
            return False, f"Gagal cek metadata OpenRouter: {exc}"
        if not metadata:
            return False, f"Model `{model}` tidak ditemukan di OpenRouter Models API."
        supported = set(metadata.get("supported_parameters") or [])
        if supported & REASONING_PARAMETERS:
            return True, f"Model `{model}` mendukung thinking."
        return False, f"Model `{model}` tidak mengiklankan parameter reasoning."

    if provider == "gemini":
        lowered = model.lower()
        if "gemini-3" in lowered or "gemini-2.5" in lowered:
            return True, f"Model `{model}` mendukung Gemini thinking."
        return False, f"Model Gemini `{model}` tidak mendukung adapter thinkingLevel/thinkingBudget."

    if provider == "openai":
        if _is_openai_reasoning_model(model):
            return True, f"Model OpenAI `{model}` mendukung reasoning effort."
        return False, f"Model OpenAI `{model}` tidak tampak sebagai reasoning model."

    return False, f"Provider `{provider}` tidak punya adapter effort."


def _openrouter_model_metadata(model_id: str) -> dict[str, Any] | None:
    response = requests.get("https://openrouter.ai/api/v1/models", timeout=8)
    response.raise_for_status()
    data = response.json().get("data", [])
    if not isinstance(data, list):
        return None
    for model in data:
        if isinstance(model, dict) and model.get("id") == model_id:
            return model
    return None


def _fallback_thinking_support(model_id: str) -> bool:
    lowered = model_id.lower()
    indicators = (
        "gpt-5",
        "o1",
        "o3",
        "o4",
        "r1",
        "reason",
        "thinking",
        "gemini-2.5",
        "gemini-3",
        "grok",
        "claude",
    )
    return any(indicator in lowered for indicator in indicators)


def _gemini_effort_mapping(model: str, requested: str) -> EffortMapping:
    lowered = model.lower()
    if "gemini-3" in lowered:
        provider_effort = "high" if requested == "xhigh" else requested
        note = "Gemini thinkingLevel tidak punya xhigh; xhigh dikirim sebagai high." if requested == "xhigh" else ""
        return EffortMapping(
            requested_effort=requested,
            provider_effort=provider_effort,
            field_path="generationConfig.thinkingConfig.thinkingLevel",
            payload_fragment={"generationConfig": {"thinkingConfig": {"thinkingLevel": provider_effort}}},
            note=note,
        )
    if "gemini-2.5" in lowered:
        budget = GEMINI_25_BUDGETS[requested]
        return EffortMapping(
            requested_effort=requested,
            provider_effort=str(budget),
            field_path="generationConfig.thinkingConfig.thinkingBudget",
            payload_fragment={"generationConfig": {"thinkingConfig": {"thinkingBudget": budget}}},
            note="Gemini 2.5 memakai thinkingBudget; effort dipetakan ke budget token.",
        )
    raise EffortUnsupportedError(
        f"Model Gemini `{model}` tidak mendukung adapter effort. "
        "Gunakan model Gemini 2.5/3 thinking atau matikan dengan /effort off."
    )


def _is_openai_reasoning_model(model: str) -> bool:
    lowered = model.lower()
    return lowered.startswith(("o1", "o3", "o4", "gpt-5")) or "codex" in lowered


def _deep_merge(target: dict[str, Any], fragment: dict[str, Any]) -> None:
    for key, value in fragment.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)
