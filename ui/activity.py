from __future__ import annotations

import itertools
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .layout import shorten_middle
from .theme import UiMode


THINKING_PHRASES = [
    "membaca konteks",
    "menyusun langkah",
    "memeriksa tool",
    "menjaga izin tetap eksplisit",
    "menunggu provider",
    "merapikan jawaban",
]


@contextmanager
def thinking_status(console, config: dict[str, Any], ui_mode: UiMode, attached_files: int = 0) -> Iterator[None]:
    if not config.get("ui", {}).get("show_spinner", True):
        yield
        return

    stop = threading.Event()
    model = shorten_middle(str(config.get("model", "model")), 28 if ui_mode.compact else 42)
    provider = str(config.get("provider", "provider"))
    spinner = "dots12" if ui_mode.unicode else "dots"
    started = time.monotonic()
    phrases = itertools.cycle(THINKING_PHRASES)
    first = next(phrases)
    status = console.status(_message(first, provider, model, started, attached_files), spinner=spinner, spinner_style="nyala.ai")

    def refresh() -> None:
        current = first
        last_phrase_change = 0.0
        while not stop.wait(0.25):
            elapsed = time.monotonic() - started
            if elapsed - last_phrase_change >= 1.4:
                current = next(phrases)
                last_phrase_change = elapsed
            status.update(_message(current, provider, model, started, attached_files))
            set_terminal_title(console, f"Nyala working - {current}")

    status.start()
    thread = threading.Thread(target=refresh, daemon=True)
    thread.start()
    set_terminal_title(console, "Nyala working")
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=0.6)
        status.stop()
        set_terminal_title(console, "Nyala ready")


def _message(phrase: str, provider: str, model: str, started: float, attached_files: int) -> str:
    elapsed = int(time.monotonic() - started)
    attach = f" | {attached_files} file" if attached_files else ""
    return f"[nyala.ai]Nyala thinking[/nyala.ai] [nyala.dim]{elapsed:02d}s[/nyala.dim] [nyala.cyan]{provider}[/nyala.cyan] [nyala.blue]{model}[/nyala.blue] [nyala.dim]| {phrase}{attach}[/nyala.dim]"


def set_terminal_title(console, title: str) -> None:
    try:
        console.file.write(f"\033]0;{title}\007")
        console.file.flush()
    except Exception:
        return
