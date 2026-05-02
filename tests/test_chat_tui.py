from __future__ import annotations

from ui.chat_tui import TranscriptConsole
from ui.commands import help_table


def test_transcript_console_accepts_nyala_theme_styles() -> None:
    captured: list[tuple[str, str]] = []
    console = TranscriptConsole(lambda kind, text: captured.append((kind, text)), width=72)

    console.print("[nyala.dim]dim[/nyala.dim] [nyala.cyan]cyan[/nyala.cyan]")
    console.print(help_table())

    assert captured[0] == ("system", "dim cyan")
    assert "NyalaCLI Slash Commands" in captured[1][1]
    assert "/exit | /quit" in captured[1][1]
