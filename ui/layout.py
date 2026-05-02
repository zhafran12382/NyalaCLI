from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text

from core.permissions import safe_path_display
from core.token_counter import estimate_messages

from .theme import UiMode


TOKEN_TARGET = 1_000_000


def clear_terminal(console: Any) -> None:
    if getattr(console, "is_terminal", False):
        console.file.write("\033[2J\033[3J\033[H")
        console.file.flush()
        return
    console.clear()


def status_bar(config: dict[str, Any], session, ui_mode: UiMode, platform_info) -> Text:
    workspace = safe_path_display(Path(config.get("workspace", platform_info.default_workspace)))
    tokens = estimate_messages(session.messages)
    provider = config.get("provider", "openrouter")
    model = config.get("model", "model")
    safety = config.get("safety_mode", "balanced")
    effort = str(config.get("thinking_effort") or "")
    meter = context_meter(tokens, ui_mode)
    token_style = token_meter_style(tokens)
    ready = "◇" if ui_mode.unicode else "*"
    text = Text()
    text.append(f"{ready} ", style="nyala.lime")
    text.append(str(provider), style="nyala.cyan")
    text.append(" ")
    text.append(shorten_middle(str(model), 24 if ui_mode.compact else 34), style="nyala.blue")
    text.append(" ")
    text.append(str(safety), style=safety_style(str(safety)))
    if effort:
        text.append(" ")
        text.append(f"think:{effort}", style="nyala.token.high")
    text.append(" ")
    text.append(meter, style=token_style)
    text.append(f" {tokens} tok", style=token_style)
    if not ui_mode.compact and ui_mode.width >= 96:
        text.append("  ")
        text.append(shorten_middle(workspace, max(24, ui_mode.width // 3)), style="nyala.purple")
    return text


def prompt_prefix(config: dict[str, Any], ui_mode: UiMode) -> str:
    workspace = safe_path_display(Path(config.get("workspace", ".")))
    safety = str(config.get("safety_mode", "balanced"))
    if ui_mode.unicode:
        return f"nyala {safety} {workspace} › "
    return f"nyala {safety} {workspace} > "


def context_meter(tokens: int, ui_mode: UiMode, limit: int = TOKEN_TARGET) -> str:
    width = 8 if ui_mode.compact else 14
    ratio = min(max(tokens / limit, 0), 1)
    filled = int(round(ratio * width))
    if ui_mode.unicode:
        return "█" * filled + "░" * (width - filled)
    return "#" * filled + "-" * (width - filled)


def token_meter_style(tokens: int, limit: int = TOKEN_TARGET) -> str:
    ratio = min(max(tokens / limit, 0), 1)
    if ratio >= 0.8:
        return "nyala.token.max"
    if ratio >= 0.45:
        return "nyala.token.high"
    if ratio >= 0.1:
        return "nyala.token.mid"
    return "nyala.token.low"


def safety_style(safety: str) -> str:
    if safety == "safe":
        return "nyala.lime"
    if safety == "freedom":
        return "nyala.warn"
    return "nyala.green"


def shorten_middle(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    if max_len <= 8:
        return text[:max_len]
    keep = max_len - 3
    start = keep // 2
    end = keep - start
    return f"{text[:start]}...{text[-end:]}"
