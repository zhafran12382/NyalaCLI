from __future__ import annotations

import shutil
from dataclasses import dataclass

from rich.console import Console
from rich.theme import Theme

from core.platform import terminal_supports_unicode


NYALA_THEME = Theme(
    {
        "nyala.cyan": "bold #5fd7ff",
        "nyala.blue": "bold #87afff",
        "nyala.purple": "bold #af87ff",
        "nyala.green": "#87d787",
        "nyala.lime": "#5fffaf",
        "nyala.orange": "#ffd75f",
        "nyala.rose": "#ff87af",
        "nyala.dim": "#7f8792",
        "nyala.text": "#d7d7d7",
        "nyala.muted": "#a8b0bb",
        "nyala.warn": "yellow",
        "nyala.error": "bold red",
        "nyala.token.low": "dim green",
        "nyala.token.mid": "green",
        "nyala.token.high": "bright_green",
        "nyala.token.max": "bold bright_green",
        "nyala.panel": "#4b6473",
        "nyala.startup.border": "#5fd7ff",
        "nyala.tool": "#d787ff",
        "nyala.ai": "bold #5fd7ff",
        "nyala.ai.marker": "#87d787",
        "nyala.user": "bold #d7ffff",
        "nyala.logo": "bold #5fd7ff",
        "markdown.paragraph": "#d7d7d7",
        "markdown.h1": "bold #5fd7ff",
        "markdown.h2": "bold #87afff",
        "markdown.h3": "bold #87d787",
        "markdown.h4": "bold #ffd75f",
        "markdown.h5": "bold #ffd75f",
        "markdown.h6": "bold #ffd75f",
        "markdown.strong": "bold #ffffff",
        "markdown.em": "italic #d7d7af",
        "markdown.code": "bold #ffd75f on #303641",
        "markdown.code_block": "#d7dee8 on #1c2028",
        "markdown.block_quote": "italic #a8b0bb",
        "markdown.item": "#d7d7d7",
        "markdown.item.bullet": "#5fd7ff",
        "markdown.item.number": "#5fd7ff",
        "markdown.link": "underline #5fd7ff",
        "markdown.link_url": "underline #87afff",
        "markdown.kbd": "bold #ffd75f on #242830",
        "markdown.table.border": "#4b6473",
        "markdown.table.header": "bold #ffd75f",
    }
)


@dataclass
class UiMode:
    unicode: bool
    compact: bool
    width: int
    height: int


def make_console() -> Console:
    return Console(theme=NYALA_THEME, highlight=False)


def detect_ui_mode(config: dict | None = None) -> UiMode:
    config = config or {}
    size = shutil.get_terminal_size((80, 24))
    ui = config.get("ui", {}) if isinstance(config.get("ui", {}), dict) else {}
    unicode_setting = ui.get("unicode", "auto")
    compact_setting = ui.get("compact", "auto")
    unicode_enabled = terminal_supports_unicode() if unicode_setting == "auto" else bool(unicode_setting)
    compact = size.columns < 72 or size.lines < 24 if compact_setting == "auto" else bool(compact_setting)
    return UiMode(unicode=unicode_enabled, compact=compact, width=size.columns, height=size.lines)


def panel_box(ui_mode: UiMode):
    from rich import box

    if not ui_mode.unicode:
        return box.ASCII
    return box.ROUNDED if not ui_mode.compact else box.SIMPLE_HEAVY
