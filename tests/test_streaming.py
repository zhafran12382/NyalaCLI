from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.router import CommandRouter
from providers.base import collect_openai_stream
from ui.chat_tui import _format_block
from ui.markdown_renderer import strip_style_markers
from ui.theme import UiMode


class FakeStreamResponse:
    def iter_lines(self, decode_unicode: bool = True):
        yield 'data: {"choices":[{"delta":{"content":"Hel"}}]}'
        yield 'data: {"choices":[{"delta":{"content":"lo"}}]}'
        yield "data: [DONE]"


class FakeConfigManager:
    def __init__(self) -> None:
        self.saved = None

    def save(self, config):
        self.saved = dict(config)


class FakeConsole:
    def __init__(self) -> None:
        self.rows = []

    def print(self, *objects, **_kwargs) -> None:
        self.rows.append(objects)


def test_collect_openai_stream_emits_deltas() -> None:
    deltas: list[str] = []

    response = collect_openai_stream(FakeStreamResponse(), deltas.append)

    assert response.content == "Hello"
    assert deltas == ["Hel", "lo"]
    assert response.raw == {"stream": True, "events": 2}


def test_stream_command_updates_config() -> None:
    config = {"stream": False}
    manager = FakeConfigManager()
    router = CommandRouter(
        {
            "console": FakeConsole(),
            "ui_mode": UiMode(True, False, 80, 24),
            "config": config,
            "config_manager": manager,
            "session": SimpleNamespace(messages=[], last_response_tokens=0),
            "session_manager": SimpleNamespace(),
            "skills": {},
            "platform_info": SimpleNamespace(),
            "project_root": Path("."),
        }
    )

    outcome = router.handle("/stream true")

    assert outcome.handled is True
    assert config["stream"] is True
    assert manager.saved and manager.saved["stream"] is True


def test_system_blocks_wrap_inside_transcript_width() -> None:
    rendered = _format_block(
        "system",
        "This is a very long system message that should wrap cleanly instead of running past the edge of a narrow terminal.",
        UiMode(True, True, 42, 16),
        42,
    )

    assert max(len(line) for line in rendered.splitlines()) <= 42


def test_assistant_block_does_not_leak_transcript_rail() -> None:
    rendered = strip_style_markers(
        _format_block(
            "assistant",
            "Ringkasan Berita:\\n\\n1. Demo May Day â<86><92> Polda Metro Jaya.",
            UiMode(True, False, 80, 24),
            80,
        )
    )

    assert "Nyala" in rendered
    assert "◆" not in rendered
    assert "  │" not in rendered
    assert "→" in rendered
