from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.align import Align
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from core import __version__
from core.permissions import safe_path_display

from .layout import shorten_middle
from .theme import NYALA_THEME, UiMode, panel_box


ASCII_LOGO = r""" _   _             _        ____ _     ___
| \ | |_   _  __ _| | __ _ / ___| |   |_ _|
|  \| | | | |/ _` | |/ _` | |   | |    | |
| |\  | |_| | (_| | | (_| | |___| |___ | |
|_| \_|\__, |\__,_|_|\__,_|\____|_____|___|
       |___/"""

COMPACT_ASCII_LOGO = r""" _  _          _        ___ _    ___
| \| |_  _ __ _| |__ _ / __| |  |_ _|
| .` | || / _` | / _` | (__| |__ | |
|_|\_|\_, \__,_|_\__,_|\___|____|___|
     |__/"""

TAGLINE = "Terminal AI assistant for workspace chat, safe tools, resumable sessions, and provider routing."
SHORT_TAGLINE = "AI chat, tools, sessions, and provider routing."
TINY_TAGLINE = "Terminal AI assistant for chat and tools."
QUIT_HINT = "/quit or Ctrl+C"
FULL_HINT = "/help commands   @file attach   !cmd shell   /quit or Ctrl+C"
VALUE_PROPS = [
    ("workspace", "context-aware"),
    ("tools", "permissioned"),
    ("sessions", "resumable"),
]


@dataclass(frozen=True)
class StartupLayout:
    tier: str
    width: int
    height: int
    content_width: int
    padding: tuple[int, int]
    show_logo: bool
    show_model: bool
    show_mode: bool
    show_workspace: bool
    show_props: bool


def print_banner(console, ui_mode: UiMode, compact: bool = False) -> None:
    if compact or ui_mode.compact:
        text = Text("NyalaCLI", style="nyala.cyan")
        text.append("  ")
        text.append(f"v{__version__}", style="nyala.orange")
        text.append("  ")
        text.append("/help", style="nyala.green")
        text.append("  ")
        text.append(QUIT_HINT, style="nyala.dim")
        console.print(Panel(text, box=panel_box(ui_mode), border_style="nyala.panel", padding=(0, 1)))
        return
    logo_art = COMPACT_ASCII_LOGO if ui_mode.width < 52 else ASCII_LOGO
    body = Text()
    body.append(logo_art, style="nyala.logo")
    body.append("\n")
    body.append(f"NyalaCLI v{__version__}", style="nyala.orange")
    body.append("  ")
    body.append(TAGLINE, style="nyala.text")
    body.append("\n")
    body.append(f" {FULL_HINT}", style="nyala.dim")

    props = Table.grid(expand=True)
    props.add_column(justify="center")
    props.add_column(justify="center")
    props.add_column(justify="center")
    props.add_row(*[_prop(label, value) for label, value in VALUE_PROPS])
    content = Table.grid(expand=True)
    content.add_row(Align.center(body))
    content.add_row(props)
    console.print(
        Panel(
            content,
            box=panel_box(ui_mode),
            border_style="nyala.panel",
            padding=(1, 2),
        )
    )


def print_startup_box(
    console,
    config: dict[str, Any],
    platform_info,
    ui_mode: UiMode,
    version: str = __version__,
) -> None:
    console.print(startup_box(config, platform_info, ui_mode, version))


def startup_box(config: dict[str, Any], platform_info, ui_mode: UiMode, version: str = __version__) -> Panel:
    layout = _startup_layout(ui_mode)
    provider = str(config.get("provider", "provider"))
    model_limit = max(10, min(42, layout.content_width - len(provider) - 5))
    model = shorten_middle(str(config.get("model", "model")), model_limit)
    safety = str(config.get("safety_mode", "balanced"))
    workspace = safe_path_display(Path(config.get("workspace", platform_info.default_workspace)).expanduser())
    workspace = shorten_middle(workspace, max(10, min(52, layout.content_width - 11)))

    content = _startup_content(layout, provider, model, safety, workspace, version)
    return Panel(
        content,
        title=None if layout.tier == "tiny" else " NyalaCLI ",
        border_style="nyala.startup.border",
        box=_startup_panel_box(ui_mode),
        padding=layout.padding,
    )


def render_startup_box_text(
    config: dict[str, Any],
    platform_info,
    ui_mode: UiMode,
    version: str = __version__,
) -> str:
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        width=max(16, ui_mode.width),
        force_terminal=False,
        color_system=None,
        theme=NYALA_THEME,
        highlight=False,
    )
    console.print(startup_box(config, platform_info, ui_mode, version))
    return "\n".join(line.rstrip() for line in buffer.getvalue().splitlines()).strip("\n")


def _prop(label: str, value: str) -> Text:
    text = Text(label, style="nyala.dim")
    text.append(" ")
    text.append(value, style="nyala.cyan")
    return text


def _startup_layout(ui_mode: UiMode) -> StartupLayout:
    width = max(16, ui_mode.width)
    height = max(8, ui_mode.height)
    tiny = width < 40 or height < 13
    compact = tiny or ui_mode.compact or width < 64 or height < 18
    pad = (0, 1) if compact else (1, 2)
    content_width = max(8, width - 2 - (pad[1] * 2))
    show_logo = not tiny and content_width >= len(COMPACT_ASCII_LOGO.splitlines()[0]) and height >= 15
    return StartupLayout(
        tier="tiny" if tiny else "compact" if compact else "wide",
        width=width,
        height=height,
        content_width=content_width,
        padding=pad,
        show_logo=show_logo,
        show_model=not tiny and height >= 14,
        show_mode=not tiny and height >= 15,
        show_workspace=not compact and height >= 20,
        show_props=not compact and height >= 22,
    )


def _startup_content(
    layout: StartupLayout,
    provider: str,
    model: str,
    safety: str,
    workspace: str,
    version: str,
) -> Group | Table:
    if layout.tier == "tiny":
        title = Text("NyalaCLI", style="nyala.logo")
        title.append(f" v{version}", style="nyala.orange")
        summary = Text(shorten_middle(TINY_TAGLINE, layout.content_width), style="nyala.text")
        hint = Text(shorten_middle(f"/help  {QUIT_HINT}", layout.content_width), style="nyala.dim")
        return Group(Align.center(title), summary, hint)

    logo_art = _logo_for(layout)
    summary_text = TAGLINE if layout.tier == "wide" else SHORT_TAGLINE
    summary = Text(summary_text, style="nyala.text")

    meta = Table.grid(expand=True, padding=(0, 2))
    meta.add_column(style="nyala.dim", no_wrap=True)
    meta.add_column(style="nyala.text")
    meta.add_row("version", f"[nyala.orange]v{version}[/nyala.orange]")
    if layout.show_model:
        meta.add_row("model", f"[nyala.purple]{provider}[/nyala.purple] [nyala.dim]/[/nyala.dim] [nyala.blue]{model}[/nyala.blue]")
    if layout.show_mode:
        meta.add_row("mode", f"[nyala.green]{safety}[/nyala.green]")
    if layout.show_workspace:
        meta.add_row("workspace", f"[nyala.rose]{workspace}[/nyala.rose]")

    hint = Text(FULL_HINT if layout.tier == "wide" else f"/help   @file   !cmd   {QUIT_HINT}", style="nyala.dim")

    content = Table.grid(expand=True)
    if layout.show_logo:
        content.add_row(Align.center(Text(logo_art, style="nyala.logo")))
    else:
        compact_title = Text("NyalaCLI", style="nyala.logo")
        compact_title.append(f" v{version}", style="nyala.orange")
        content.add_row(Align.center(compact_title))
    content.add_row(summary)
    content.add_row(meta)
    if layout.show_props:
        props = Table.grid(expand=True)
        props.add_column(justify="center")
        props.add_column(justify="center")
        props.add_column(justify="center")
        props.add_row(*[_prop(label, value) for label, value in VALUE_PROPS])
        content.add_row(props)
    content.add_row(hint)
    return content


def _logo_for(layout: StartupLayout) -> str:
    full_width = max(len(line) for line in ASCII_LOGO.splitlines())
    if layout.tier == "wide" and layout.content_width >= full_width and layout.height >= 18:
        return ASCII_LOGO
    return COMPACT_ASCII_LOGO


def _startup_panel_box(ui_mode: UiMode):
    from rich import box

    if not ui_mode.unicode:
        return box.ASCII
    return box.ROUNDED
