from __future__ import annotations

import io
import threading
import textwrap
import time
from pathlib import Path
from typing import Any, Callable

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Float, FloatContainer, HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea
from rich.console import Console

from core import __version__
from core.agent import Agent
from core.permissions import PermissionManager
from core.prompt_context import attachment_notice, build_file_context
from core.router import CommandRouter
from core.session import Session
from skills.base import SkillResult
from ui.activity import set_terminal_title
from ui.autocomplete import NyalaCompleter
from ui.banner import render_startup_box_text
from ui.input_state import InputDraftState, install_paste_guard
from ui.layout import shorten_middle, status_bar
from ui.markdown_renderer import STYLE_END, STYLE_MARK, assistant_transcript_text, normalize_terminal_text, split_line_style
from ui.panels import print_tool
from ui.theme import NYALA_THEME, UiMode


_ASSISTANT_PREFIXES = ("  │ ", "  | ")
_ASSISTANT_GUIDES = ("  │", "  |")
_LINE_STYLE_CLASSES = {
    "H1": "class:transcript.md.h1",
    "H2": "class:transcript.md.h2",
    "H3": "class:transcript.md.h3",
    "HR": "class:transcript.md.rule",
    "QUOTE": "class:transcript.md.quote",
    "LIST": "class:transcript.md.list",
    "CODE": "class:transcript.md.code",
    "CODE_BORDER": "class:transcript.md.code.border",
    "TABLE": "class:transcript.md.table",
    "TABLE_HEADER": "class:transcript.md.table.header",
    "TABLE_BORDER": "class:transcript.md.table.border",
}
_INLINE_STYLE_CLASSES = {
    "B": "class:transcript.md.bold",
    "I": "class:transcript.md.italic",
    "C": "class:transcript.md.inline-code",
    "L": "class:transcript.md.link",
    "U": "class:transcript.md.strike",
}
_BUSY_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_ASCII_BUSY_FRAMES = ("-", "\\", "|", "/")


class TranscriptConsole:
    def __init__(
        self,
        append: Callable[[str, str], None],
        width: int = 80,
        confirm: Callable[[str, bool], bool] | None = None,
    ) -> None:
        self._append = append
        self.width = width
        self._confirm = confirm
        self.file = io.StringIO()
        self.is_terminal = False

    def print(self, *objects: Any, **kwargs: Any) -> None:
        buffer = io.StringIO()
        console = Console(
            file=buffer,
            width=self.width,
            force_terminal=False,
            color_system=None,
            theme=NYALA_THEME,
            highlight=False,
        )
        console.print(*objects, **kwargs)
        text = buffer.getvalue().rstrip()
        if text:
            self._append("system", text)

    def clear(self) -> None:
        self._append("clear", "")

    def confirm(self, message: str, default: bool = False) -> bool:
        if self._confirm:
            return self._confirm(message, default)
        return default

    def status(self, *_args: Any, **_kwargs: Any):
        return _NoopStatus()


class _NoopStatus:
    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def update(self, *_args: Any, **_kwargs: Any) -> None:
        return

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.stop()


class TranscriptLexer(Lexer):
    def lex_document(self, document):
        def get_line(lineno: int):
            line = document.lines[lineno]
            stripped = line.strip()
            if stripped in {"Nyala", "◆ Nyala", "* Nyala"}:
                return [("class:transcript.label.ai", line)]
            if stripped == "You":
                return [("class:transcript.label.user", line)]
            if stripped == "System":
                return [("class:transcript.label.system", line)]
            if stripped == "Error":
                return [("class:transcript.label.error", line)]
            if stripped == "Tool":
                return [("class:transcript.label.tool", line)]
            for prefix in _ASSISTANT_PREFIXES:
                if line.startswith(prefix):
                    body_style, body = split_line_style(line[len(prefix) :])
                    base_style = _LINE_STYLE_CLASSES.get(body_style, "class:transcript.assistant")
                    return [("class:transcript.guide", prefix)] + _marked_fragments(body, base_style)
            if line in _ASSISTANT_GUIDES:
                return [("class:transcript.guide", line)]
            if line.startswith("  "):
                body_style, body = split_line_style(line[2:])
                if body_style is not None or STYLE_MARK in body:
                    base_style = _LINE_STYLE_CLASSES.get(body_style, "class:transcript.assistant")
                    return [("class:transcript", "  ")] + _marked_fragments(body, base_style)
            if stripped.startswith(("╭", "╰", "├", "┤", "─", "+", "-")):
                return [("class:transcript.panel", line)]
            if line.startswith(("│", "|")) and len(line) > 1:
                return [
                    ("class:transcript.panel", line[:1]),
                    ("class:transcript", line[1:-1]),
                    ("class:transcript.panel", line[-1:]),
                ]
            return [("class:transcript", line)]

        return get_line


class ChatTUI:
    def __init__(
        self,
        *,
        config_manager,
        platform_info,
        config: dict[str, Any],
        session: Session,
        session_manager,
        skills: dict[str, Any],
        project_root: Path,
        ui_mode: UiMode,
        doctor_callback: Callable[[], None] | None = None,
        provider_validator: Callable[[dict[str, Any]], tuple[bool, str]] | None = None,
    ) -> None:
        self.config_manager = config_manager
        self.platform_info = platform_info
        self.config = config
        self.session = session
        self.session_manager = session_manager
        self.skills = skills
        self.project_root = project_root
        self.ui_mode = ui_mode
        self.doctor_callback = doctor_callback
        self.provider_validator = provider_validator
        self.history_path = platform_info.cache_dir / "prompt_history.txt"
        self._lines: list[str] = []
        self._lock = threading.RLock()
        self._follow_output = True
        self._busy = False
        self._status = "ready"
        self._busy_started = 0.0
        self._last_latency = 0.0
        self._confirm_event: threading.Event | None = None
        self._confirm_result = False
        self._confirm_default = False
        self._draft_state = InputDraftState()
        self._startup_shown = False
        self._exiting = False
        self._stream_start_index: int | None = None
        self._stream_text = ""
        self._stream_rendered_len = 0
        self._stream_last_render = 0.0

        self.transcript_console = TranscriptConsole(self._append_rendered, width=ui_mode.width, confirm=self._confirm)
        self.transcript = TextArea(
            text="",
            read_only=True,
            focusable=False,
            scrollbar=True,
            wrap_lines=True,
            lexer=TranscriptLexer(),
            style="class:transcript",
        )
        self.composer = TextArea(
            multiline=False,
            wrap_lines=False,
            height=Dimension.exact(1),
            dont_extend_height=True,
            prompt=FormattedText([("class:composer.prompt", "  › ")]),
            completer=NyalaCompleter(self.config.get("workspace", ".")),
            complete_while_typing=True,
            history=FileHistory(str(self.history_path)),
            style="class:composer.input",
        )
        install_paste_guard(self.composer.buffer, self._draft_state, self._invalidate)
        self.app = self._build_application()

    def run(self) -> int:
        if not self._startup_shown:
            self._append("startup", render_startup_box_text(self.config, self.platform_info, self.ui_mode, __version__))
            self._startup_shown = True
        set_terminal_title(self.transcript_console, "Nyala ready")
        try:
            result = self.app.run()
        except KeyboardInterrupt:
            self.session_manager.save(self.session)
            set_terminal_title(self.transcript_console, "Nyala exit")
            return 0
        return int(result or 0)

    def _build_application(self) -> Application:
        root = FloatContainer(
            content=HSplit(
                [
                    Window(FormattedTextControl(self._header_fragments), height=1, style="class:header"),
                    Window(FormattedTextControl(self._divider_fragments), height=1),
                    self.transcript,
                    self.composer,
                    Window(FormattedTextControl(self._footer_fragments), height=1, style="class:footer"),
                ]
            ),
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=8, scroll_offset=1),
                )
            ],
        )
        return Application(
            layout=Layout(root, focused_element=self.composer),
            key_bindings=self._key_bindings(),
            style=_style(),
            full_screen=True,
            mouse_support=True,
            refresh_interval=0.25,
        )

    def _key_bindings(self) -> KeyBindings:
        bindings = KeyBindings()

        @bindings.add("enter")
        def _(event) -> None:
            if self._confirm_event:
                self._resolve_confirm(self._confirm_default)
                return
            buffer = self.composer.buffer
            if _apply_current_completion(buffer):
                return
            self._submit()

        @bindings.add("tab")
        def _(event) -> None:
            buffer = self.composer.buffer
            if not _apply_current_completion(buffer):
                buffer.start_completion(select_first=True)

        @bindings.add("escape")
        def _(event) -> None:
            if self._confirm_event:
                self._resolve_confirm(False)
                return
            if self._draft_state.placeholder_active:
                self.composer.buffer.reset()
                return
            if self.composer.buffer.complete_state:
                self.composer.buffer.cancel_completion()

        @bindings.add("escape", "enter")
        def _(event) -> None:
            if self._draft_state.placeholder_active:
                self.composer.buffer.reset()

        @bindings.add("c-l")
        def _(event) -> None:
            self._clear_transcript()

        @bindings.add("c-c", eager=True)
        def _(event) -> None:
            self._exit_chat("Ctrl+C")

        @bindings.add("c-q", eager=True)
        def _(event) -> None:
            self._exit_chat("Ctrl+Q")

        @bindings.add("y")
        def _(event) -> None:
            if self._confirm_event:
                self._resolve_confirm(True)
            else:
                self.composer.buffer.insert_text("y")

        @bindings.add("n")
        def _(event) -> None:
            if self._confirm_event:
                self._resolve_confirm(False)
            else:
                self.composer.buffer.insert_text("n")

        @bindings.add("pageup")
        @bindings.add("c-b")
        def _(event) -> None:
            self._scroll_transcript(-max(3, self.ui_mode.height - 8))

        @bindings.add("pagedown")
        @bindings.add("c-f")
        def _(event) -> None:
            self._scroll_transcript(max(3, self.ui_mode.height - 8))

        @bindings.add("home")
        def _(event) -> None:
            self._scroll_to_top()

        @bindings.add("end")
        @bindings.add("c-end")
        def _(event) -> None:
            self._scroll_to_bottom()

        return bindings

    def _submit(self) -> None:
        if self._busy:
            self._append("system", "Still working. Wait for the current turn to finish.")
            return
        raw_text = self._draft_state.submission_text(self.composer.text)
        display_text = self._draft_state.display_text(self.composer.text)
        text = raw_text if self._draft_state.placeholder_active else raw_text.strip()
        if not text.strip():
            return
        self.composer.buffer.reset()
        self._follow_output = True
        self._append("user", display_text)
        thread = threading.Thread(target=self._handle_submission, args=(text,), daemon=True)
        thread.start()

    def _handle_submission(self, text: str) -> None:
        started = time.monotonic()
        self._set_busy(True, "working")
        try:
            if text == "?":
                text = "/palette"
            if text.startswith("!"):
                self._run_shell_shortcut(text[1:].strip())
                return
            if text.startswith("/"):
                self._handle_command(text)
                return
            self._handle_prompt(text)
        except Exception as exc:
            self._append("error", f"Command/input error: {exc}")
        finally:
            if not self._exiting:
                self._last_latency = time.monotonic() - started
                self._set_busy(False, "ready")
            self.session_manager.save(self.session)

    def _handle_command(self, text: str) -> None:
        router = CommandRouter(
            {
                "console": self.transcript_console,
                "ui_mode": self.ui_mode,
                "config": self.config,
                "config_manager": self.config_manager,
                "session": self.session,
                "session_manager": self.session_manager,
                "skills": self.skills,
                "platform_info": self.platform_info,
                "project_root": self.project_root,
                "doctor": self.doctor_callback,
                "provider_validator": self.provider_validator,
            }
        )
        outcome = router.handle(text)
        if outcome.session_replaced is not None:
            self.session = outcome.session_replaced
            self._append("system", f"Session loaded: {self.session.session_id}")
        if outcome.clear:
            self._clear_transcript()
        if outcome.reload_provider:
            self.config = self.config_manager.load()
            self.composer.buffer.completer = NyalaCompleter(self.config.get("workspace", "."))
        if outcome.exit_chat:
            self._exit_chat("/quit")

    def _handle_prompt(self, text: str) -> None:
        self._set_busy(True, "thinking")
        prompt_context, attachments = build_file_context(text, self.config.get("workspace", self.platform_info.default_workspace))
        notice = attachment_notice(attachments)
        if notice:
            self._append("system", notice)
        agent = Agent(
            self.config,
            self.session,
            self.skills,
            self.platform_info,
            self.transcript_console,
            self.ui_mode,
            self.project_root,
            interactive_permissions=True,
        )
        attached_count = len([item for item in attachments if item.included])
        if attached_count:
            self._set_busy(True, f"thinking · {attached_count} file")
        streamed = False

        def on_delta(delta: str) -> None:
            nonlocal streamed
            if not streamed:
                self._begin_assistant_stream()
                streamed = True
            self._append_assistant_stream_delta(delta)

        answer = agent.handle(text, prompt_context, on_delta=on_delta if self.config.get("stream", False) else None)
        if streamed:
            self._finish_assistant_stream(answer)
        else:
            self._append("assistant", answer)

    def _run_shell_shortcut(self, command: str) -> None:
        if not command:
            self._append("error", "Pakai: !<command>")
            return
        skill = self.skills.get("bash_exec")
        if not skill:
            self._append("error", "Skill bash_exec tidak tersedia.")
            return
        context = {
            "workspace": self.config.get("workspace", str(self.platform_info.default_workspace)),
            "config": self.config,
            "safety_mode": self.config.get("safety_mode", "balanced"),
            "console": self.transcript_console,
            "platform_info": self.platform_info,
            "permission": PermissionManager(self.config.get("safety_mode", "balanced"), interactive=True),
            "project_root": self.project_root,
            "max_output_length": 3000 if self.ui_mode.compact else 6000,
        }
        self.session.add("user", f"!{command}", {"shell_shortcut": True})
        print_tool(self.transcript_console, "bash_exec", {"command": command}, "running", self.ui_mode)
        try:
            result = skill.run({"command": command}, context)
        except Exception as exc:
            result = SkillResult(False, f"Tool error: {exc}")
        print_tool(self.transcript_console, "bash_exec", {"command": command}, "done" if result.ok else "error", self.ui_mode, result.output)
        self.session.add("tool", result.output, {"tool": "bash_exec", "ok": result.ok, "shell_shortcut": True})

    def _append_rendered(self, kind: str, text: str) -> None:
        self._append(kind, text)

    def _append(self, kind: str, text: str) -> None:
        if kind == "clear":
            self._clear_transcript()
            return
        with self._lock:
            block = _format_block(kind, text, self.ui_mode, self.ui_mode.width)
            self._lines.extend(block.splitlines() or [""])
            self._trim_transcript()
            self._sync_transcript_text()
        self.app.invalidate()

    def _begin_assistant_stream(self) -> None:
        with self._lock:
            self._follow_output = True
            self._stream_start_index = len(self._lines)
            self._stream_text = ""
            self._stream_rendered_len = 0
            self._stream_last_render = 0.0
            self._render_assistant_stream_locked(force=True)
            self._sync_transcript_text()
        self.app.invalidate()

    def _append_assistant_stream_delta(self, delta: str) -> None:
        with self._lock:
            if self._stream_start_index is None:
                self._stream_start_index = len(self._lines)
            self._stream_text += delta
            now = time.monotonic()
            pending = len(self._stream_text) - self._stream_rendered_len
            if pending < 80 and now - self._stream_last_render < 0.05:
                return
            self._render_assistant_stream_locked()
            self._sync_transcript_text()
        self.app.invalidate()

    def _finish_assistant_stream(self, answer: str) -> None:
        with self._lock:
            if self._stream_start_index is None:
                self._append("assistant", answer)
                return
            self._stream_text = answer
            self._render_assistant_stream_locked(force=True)
            self._stream_start_index = None
            self._stream_text = ""
            self._stream_rendered_len = 0
            self._sync_transcript_text()
        self.app.invalidate()

    def _render_assistant_stream_locked(self, force: bool = False) -> None:
        if self._stream_start_index is None:
            return
        shown = self._stream_text if self._stream_text.strip() else ("…" if self.ui_mode.unicode else "...")
        block = _format_block("assistant", shown, self.ui_mode, self.ui_mode.width)
        block_lines = block.splitlines() or [""]
        self._lines[self._stream_start_index :] = block_lines
        self._stream_rendered_len = len(self._stream_text)
        self._stream_last_render = 0.0 if force else time.monotonic()

    def _clear_transcript(self) -> None:
        with self._lock:
            self._lines = []
            self._follow_output = True
            self._sync_transcript_text()
        self.app.invalidate()

    def _trim_transcript(self, max_lines: int = 5000) -> None:
        if len(self._lines) > max_lines:
            self._lines = self._lines[-max_lines:]

    def _sync_transcript_text(self) -> None:
        self.transcript.text = "\n".join(self._lines)
        if self._follow_output:
            self.transcript.buffer.cursor_position = len(self.transcript.text)

    def _near_bottom(self, threshold: int = 4) -> bool:
        document = self.transcript.buffer.document
        return document.line_count - document.cursor_position_row <= threshold

    def _scroll_transcript(self, delta: int) -> None:
        document = self.transcript.buffer.document
        target = max(0, min(document.line_count - 1, document.cursor_position_row + delta))
        self.transcript.buffer.cursor_position = document.translate_row_col_to_index(target, 0)
        self._follow_output = self._near_bottom()
        self.app.invalidate()

    def _scroll_to_top(self) -> None:
        self.transcript.buffer.cursor_position = 0
        self._follow_output = False
        self.app.invalidate()

    def _scroll_to_bottom(self) -> None:
        self._follow_output = True
        self.transcript.buffer.cursor_position = len(self.transcript.text)
        self.app.invalidate()

    def _set_busy(self, busy: bool, status: str) -> None:
        self._busy = busy
        self._status = status
        if busy:
            self._busy_started = time.monotonic()
        set_terminal_title(self.transcript_console, f"Nyala {status}")
        self.app.invalidate()

    def _invalidate(self) -> None:
        app = getattr(self, "app", None)
        if app:
            app.invalidate()

    def _confirm(self, message: str, default: bool = False) -> bool:
        event = threading.Event()
        self._confirm_event = event
        self._confirm_default = default
        self._confirm_result = default
        suffix = "Y/n" if default else "y/N"
        self._append("system", f"{message}\nConfirm [{suffix}]")
        self._set_busy(True, "confirm")
        event.wait()
        self._set_busy(True, "working")
        return self._confirm_result

    def _resolve_confirm(self, value: bool) -> None:
        event = self._confirm_event
        self._confirm_result = value
        self._confirm_event = None
        self._append("system", "Confirmed." if value else "Cancelled.")
        if event:
            event.set()

    def _exit_chat(self, source: str = "") -> None:
        self._exiting = True
        event = self._confirm_event
        if event:
            self._confirm_result = False
            self._confirm_event = None
            event.set()
        try:
            self.session_manager.save(self.session)
        finally:
            self._set_busy(False, "exiting")
            set_terminal_title(self.transcript_console, "Nyala exit")
            self.app.exit(result=0)

    def _header_fragments(self):
        provider = str(self.config.get("provider", "provider"))
        model = shorten_middle(str(self.config.get("model", "model")), 28 if self.ui_mode.compact else 44)
        mode = str(self.config.get("safety_mode", "balanced"))
        effort = str(self.config.get("thinking_effort") or "")
        session = shorten_middle(self.session.session_id, 20)
        fragments = [
            ("class:header.title", " NYALA "),
            ("class:header.dim", " "),
            ("class:header.provider", provider),
            ("class:header.dim", " / "),
            ("class:header.model", model),
            ("class:header.dim", f"  {mode}"),
        ]
        if effort:
            fragments.extend([("class:header.dim", "  "), ("class:header.effort", f"think:{effort}")])
        fragments.append(("class:header.dim", f"  {session}"))
        return fragments

    def _divider_fragments(self):
        width = max(20, self.ui_mode.width)
        return [("class:divider", "─" * width if self.ui_mode.unicode else "-" * width)]

    def _footer_fragments(self):
        status = status_bar(self.config, self.session, self.ui_mode, self.platform_info).plain
        latency = f"{self._last_latency:.1f}s" if self._last_latency else ""
        hint = self._footer_hint()
        if self._draft_state.placeholder_active:
            hint = "pasted draft · Enter sends full text · Esc clears · Ctrl+C quit"
        if self._busy:
            hint = "working · input pinned · PgUp/PgDn scroll · Ctrl+C quit"
        right = f" {latency}" if latency else ""
        return [
            ("class:footer.status", f" {self._status_text()} "),
            ("class:footer.dim", status),
            ("class:footer.dim", right),
            ("class:footer.hint", f"  {hint}"),
        ]

    def _footer_hint(self) -> str:
        if self.ui_mode.width < 72:
            return "Enter send · /help · /quit · Ctrl+C"
        return "Enter send · /help commands · PgUp/PgDn scroll · /quit or Ctrl+C/Ctrl+Q"

    def _status_text(self) -> str:
        if not self._busy:
            return self._status
        frames = _BUSY_FRAMES if self.ui_mode.unicode else _ASCII_BUSY_FRAMES
        index = int((time.monotonic() - self._busy_started) * 10) % len(frames)
        return f"{frames[index]} {self._status}"


def _style() -> Style:
    return Style.from_dict(
        {
            "header": "bg:#101820 #d7ffff",
            "header.title": "bg:#5fd7ff #081018 bold",
            "header.provider": "#5fd7ff bold",
            "header.model": "#af87ff",
            "header.effort": "#ffd75f bold",
            "header.dim": "#8a8f98",
            "divider": "#3a5264",
            "transcript": "#d7d7d7",
            "transcript.assistant": "#d7d7d7",
            "transcript.guide": "#4b6473",
            "transcript.label.ai": "#5fd7ff bold",
            "transcript.label.user": "#5fffaf bold",
            "transcript.label.system": "#87afff",
            "transcript.label.error": "#ff5f5f bold",
            "transcript.label.tool": "#d787ff bold",
            "transcript.panel": "#5f8797",
            "transcript.md.h1": "#5fd7ff bold",
            "transcript.md.h2": "#87afff bold",
            "transcript.md.h3": "#87d787 bold",
            "transcript.md.bold": "#ffffff bold",
            "transcript.md.italic": "#d7d7af italic",
            "transcript.md.inline-code": "bg:#303641 #ffd75f bold",
            "transcript.md.link": "#5fd7ff underline",
            "transcript.md.strike": "#8a8f98",
            "transcript.md.rule": "#3f4b59",
            "transcript.md.quote": "#a8b0bb italic",
            "transcript.md.list": "#d7d7d7",
            "transcript.md.code": "bg:#1c2028 #d7dee8",
            "transcript.md.code.border": "#5f8797",
            "transcript.md.table": "#d7d7d7",
            "transcript.md.table.header": "#ffd75f bold",
            "transcript.md.table.border": "#4b6473",
            "composer.prompt": "bg:#2b3038 #5fd7ff bold",
            "composer.input": "bg:#2b3038 #f2f2f2",
            "footer": "bg:#101820",
            "footer.status": "bg:#163326 #5fffaf bold",
            "footer.dim": "#8a8f98",
            "footer.hint": "#87afff",
            "completion-menu.completion": "bg:#1c2028 #d7d7d7",
            "completion-menu.completion.current": "bg:#3a4452 #ffffff bold",
            "scrollbar.background": "bg:#101820",
            "scrollbar.button": "bg:#4b6473",
        }
    )


def _format_block(kind: str, text: str, ui_mode: UiMode, width: int) -> str:
    text = text.rstrip()
    if not text:
        return ""
    if kind == "startup":
        return f"\n{text}"
    label = {
        "user": "You",
        "assistant": "Nyala",
        "system": "System",
        "error": "Error",
        "tool": "Tool",
    }.get(kind, kind.title())
    body = assistant_transcript_text(text, width, ui_mode) if kind == "assistant" else _wrapped_block(text, width, ui_mode)
    return f"\n{label}\n{body}"


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" if line else "" for line in text.splitlines())


def _wrapped_block(text: str, width: int, ui_mode: UiMode) -> str:
    text = normalize_terminal_text(text, ui_mode)
    body_width = max(18, width - 4)
    wrapper = textwrap.TextWrapper(
        width=body_width,
        initial_indent="  ",
        subsequent_indent="  ",
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=True,
    )
    lines: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            lines.append("")
            continue
        if _looks_preformatted(raw_line):
            lines.append(f"  {raw_line}")
            continue
        lines.extend(wrapper.wrap(raw_line) or [""])
    return "\n".join(lines)


def _looks_preformatted(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith(("╭", "╰", "├", "┤", "│", "+", "|")):
        return True
    if set(stripped) <= {"─", "-", "━", "═", " "} and len(stripped) >= 8:
        return True
    return False


def _marked_fragments(text: str, base_style: str):
    fragments: list[tuple[str, str]] = []
    styles = [base_style]
    i = 0
    while i < len(text):
        if text[i] == STYLE_MARK and i + 1 < len(text):
            code = text[i + 1]
            style = _INLINE_STYLE_CLASSES.get(code)
            if style:
                styles.append(f"{base_style} {style}")
                i += 2
                continue
        if text[i] == STYLE_END:
            if len(styles) > 1:
                styles.pop()
            i += 1
            continue
        next_marker = _next_marker(text, i + 1)
        fragments.append((styles[-1], text[i:next_marker]))
        i = next_marker
    return fragments or [(base_style, "")]


def _next_marker(text: str, start: int) -> int:
    positions = [pos for pos in (text.find(STYLE_MARK, start), text.find(STYLE_END, start)) if pos != -1]
    return min(positions) if positions else len(text)


def _apply_current_completion(buffer: Buffer) -> bool:
    state = buffer.complete_state
    if not state or not state.current_completion:
        return False
    buffer.apply_completion(state.current_completion)
    return True
