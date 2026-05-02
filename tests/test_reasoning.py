from __future__ import annotations

import pytest

from core.reasoning import effort_display, model_supports_thinking, normalize_effort
from ui.layout import token_meter_style


def test_normalize_effort_levels() -> None:
    assert normalize_effort("Minimal") == "minimal"
    assert normalize_effort("Xhigh") == "xhigh"
    assert normalize_effort("off") == ""


def test_normalize_effort_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        normalize_effort("maximum")


def test_effort_display() -> None:
    assert effort_display("high") == "High"
    assert effort_display("") == "Off"


def test_openrouter_metadata_parse_error_falls_back_for_reasoning_model(monkeypatch) -> None:
    def broken_metadata(_model_id: str):
        raise ValueError("invalid json")

    monkeypatch.setattr("core.reasoning._openrouter_model_metadata", broken_metadata)
    ok, reason = model_supports_thinking({"provider": "openrouter", "model": "openai/gpt-5-mini"})

    assert ok is True
    assert "Gagal cek metadata OpenRouter" in reason


def test_token_meter_gets_greener_near_target() -> None:
    assert token_meter_style(1_000) == "nyala.token.low"
    assert token_meter_style(900_000) == "nyala.token.max"
