from __future__ import annotations

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .markdown_renderer import assistant_response_renderable
from .theme import UiMode, panel_box


def print_ai(console, text: str, ui_mode: UiMode) -> None:
    console.print(assistant_response_renderable(text, ui_mode))


def print_user(console, text: str, ui_mode: UiMode) -> None:
    console.print(Panel(text, title="You", border_style="nyala.user", box=panel_box(ui_mode), padding=(0, 1)))


def print_error(console, text: str, ui_mode: UiMode) -> None:
    console.print(Panel(text, title="Error", border_style="nyala.error", box=panel_box(ui_mode), padding=(0, 1)))


def print_info(console, text: str, ui_mode: UiMode, title: str = "Info") -> None:
    console.print(Panel(text, title=title, border_style="nyala.panel", box=panel_box(ui_mode), padding=(0, 1)))


def print_tool(console, name: str, args: dict, status: str, ui_mode: UiMode, output: str | None = None) -> None:
    table = Table.grid(expand=True)
    table.add_column(style="nyala.dim", ratio=1)
    table.add_column(ratio=3)
    table.add_row("tool", f"[nyala.tool]{name}[/nyala.tool]")
    table.add_row("status", _status_text(status))
    if args:
        shown = ", ".join(f"{key}={shorten(str(value))}" for key, value in args.items())
        table.add_row("args", shown)
    if output:
        table.add_row("output", shorten(output, 500))
    console.print(Panel(table, title="Tool Call", border_style=_status_border(status), box=panel_box(ui_mode), padding=(0, 1)))


def print_json(console, text: str, ui_mode: UiMode, title: str = "JSON") -> None:
    syntax = Syntax(text, "json", theme="monokai", word_wrap=True)
    console.print(Panel(syntax, title=title, border_style="nyala.purple", box=panel_box(ui_mode)))


def shorten(text: str, max_len: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."


def _status_text(status: str) -> str:
    if status == "running":
        return "[yellow]running[/yellow]"
    if status == "error":
        return "[red]error[/red]"
    if status == "done":
        return "[green]done[/green]"
    return status


def _status_border(status: str) -> str:
    if status == "error":
        return "nyala.error"
    if status == "done":
        return "nyala.green"
    return "nyala.tool"
