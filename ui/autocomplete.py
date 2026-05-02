from __future__ import annotations

import re
from pathlib import Path

from prompt_toolkit.completion import Completer, Completion


SLASH_COMMANDS = [
    "/help",
    "/home",
    "/palette",
    "/context",
    "/usage",
    "/stats",
    "/model",
    "/provider",
    "/routing",
    "/effort minimal",
    "/effort low",
    "/effort medium",
    "/effort high",
    "/effort xhigh",
    "/effort off",
    "/base-url",
    "/endpoint",
    "/provider-test",
    "/test-provider",
    "/config",
    "/stream true",
    "/stream false",
    "/skills",
    "/token",
    "/save",
    "/load",
    "/resume",
    "/continue",
    "/sessions",
    "/compact",
    "/clear",
    "/safe on",
    "/safe off",
    "/mode safe",
    "/mode balanced",
    "/mode freedom",
    "/workspace",
    "/pwd",
    "/tree",
    "/team",
    "/configure team",
    "/doctor",
    "/exit",
    "/quit",
]


class NyalaCompleter(Completer):
    def __init__(self, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace or ".").expanduser()

    def get_completions(self, document, complete_event):
        text = document.current_line_before_cursor
        if text.startswith("/"):
            yield from self._slash_completions(text)
            return
        yield from self._file_mention_completions(text)

    def _slash_completions(self, text: str):
        for command in SLASH_COMMANDS:
            if command.startswith(text):
                yield Completion(command, start_position=-len(text), display=command, display_meta="command")

    def _file_mention_completions(self, text: str):
        match = re.search(r"(^|\s)@([^\s]*)$", text)
        if not match:
            return
        typed = match.group(2)
        if typed.endswith("/"):
            base_dir = (self.workspace / typed).resolve()
            prefix = ""
        else:
            typed_path = Path(typed)
            base_dir = (self.workspace / typed_path.parent).resolve() if typed_path.parent != Path(".") else self.workspace.resolve()
            prefix = typed_path.name.lower()
        try:
            children = sorted(base_dir.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
        except OSError:
            return

        shown = 0
        for child in children:
            if shown >= 40:
                break
            if child.name in {".git", "__pycache__", ".pytest_cache"}:
                continue
            if prefix and not child.name.lower().startswith(prefix):
                continue
            try:
                relative = child.relative_to(self.workspace.resolve())
            except ValueError:
                continue
            completion = str(relative)
            meta = "dir" if child.is_dir() else "file"
            if child.is_dir():
                completion += "/"
            yield Completion(completion, start_position=-len(typed), display=f"@{completion}", display_meta=meta)
            shown += 1


class SlashCommandCompleter(NyalaCompleter):
    """Backward-compatible name for older imports."""
