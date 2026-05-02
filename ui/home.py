from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text

from core.permissions import safe_path_display

from .layout import safety_style, shorten_middle
from .theme import UiMode


def print_home_screen(
    console,
    config: dict[str, Any],
    _session,
    _session_manager,
    platform_info,
    _skills: dict,
    ui_mode: UiMode,
) -> None:
    console.print(_brand_line(ui_mode))
    console.print(_runtime_line(config, ui_mode))
    console.print(_workspace_line(config, platform_info, ui_mode))
    console.print()


def _brand_line(ui_mode: UiMode) -> Text:
    text = Text()
    text.append("NYALA", style="bold cyan")
    text.append("CLI", style="bold magenta")
    text.append("  ")
    text.append("ready", style="nyala.lime")
    if not ui_mode.compact and ui_mode.width >= 72:
        text.append("  ")
        text.append("terminal AI agent", style="nyala.dim")
    return text


def _runtime_line(config: dict[str, Any], ui_mode: UiMode) -> Text:
    marker = "▸" if ui_mode.unicode else ">"
    provider = str(config.get("provider", "openrouter"))
    model_width = 26 if ui_mode.compact else 40
    model = shorten_middle(str(config.get("model", "model")), model_width)
    safety = str(config.get("safety_mode", "balanced"))
    effort = str(config.get("thinking_effort") or "")

    text = Text()
    text.append(f"{marker} ", style="nyala.panel")
    text.append(provider, style="nyala.cyan")
    text.append(" / ", style="nyala.dim")
    text.append(model, style="nyala.blue")
    text.append("  ")
    text.append(safety, style=safety_style(safety))
    if effort:
        text.append("  ")
        text.append(f"think:{effort}", style="nyala.token.high")
    return text


def _workspace_line(config: dict[str, Any], platform_info, ui_mode: UiMode) -> Text:
    workspace = Path(config.get("workspace", platform_info.default_workspace)).expanduser()
    width = max(24, ui_mode.width - 12) if not ui_mode.compact else max(18, ui_mode.width - 10)
    text = Text()
    text.append("workspace ", style="nyala.dim")
    text.append(shorten_middle(safe_path_display(workspace), width), style="nyala.purple")
    return text
