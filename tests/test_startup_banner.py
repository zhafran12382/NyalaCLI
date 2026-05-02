from __future__ import annotations

from types import SimpleNamespace

from ui.banner import render_startup_box_text
from ui.theme import UiMode


def test_startup_box_is_single_panel_with_logo_and_version() -> None:
    config = {
        "provider": "openrouter",
        "model": "deepseek/deepseek-chat",
        "safety_mode": "balanced",
        "workspace": "/tmp/workspace",
    }
    platform = SimpleNamespace(default_workspace="/tmp/workspace")

    rendered = render_startup_box_text(config, platform, UiMode(True, False, 80, 24), "9.8.7")

    assert rendered.count("╭") == 1
    assert rendered.count("╰") == 1
    assert "NyalaCLI" in rendered
    assert "v9.8.7" in rendered
    assert "Terminal AI assistant" in rendered


def test_startup_box_adapts_to_narrow_sizes() -> None:
    config = {
        "provider": "openrouter",
        "model": "deepseek/deepseek-chat-with-a-long-name",
        "safety_mode": "balanced",
        "workspace": "/tmp/workspace/with/a/very/long/path",
    }
    platform = SimpleNamespace(default_workspace="/tmp/workspace")

    for width, height in [(28, 10), (36, 12), (42, 14), (52, 16)]:
        rendered = render_startup_box_text(config, platform, UiMode(True, True, width, height), "9.8.7")
        assert max(len(line) for line in rendered.splitlines()) <= width
        assert len(rendered.splitlines()) <= height
        assert "NyalaCLI" in rendered
        assert "v9.8.7" in rendered
        assert "/quit" in rendered or "Ctrl+C" in rendered
