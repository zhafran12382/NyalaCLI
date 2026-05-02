from __future__ import annotations

from pathlib import Path

from .autocomplete import NyalaCompleter
from .input_state import InputDraftState, install_paste_guard
from .theme import UiMode


def prompt_input(config: dict, ui_mode: UiMode, history_path: Path | None = None, status_text: str = "") -> str:
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import FormattedText
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.styles import Style

        _anchor_cursor_bottom()
        history = FileHistory(str(history_path)) if history_path else None
        draft = InputDraftState()
        bindings = KeyBindings()

        @bindings.add("enter")
        def _(event):
            event.current_buffer.validate_and_handle()

        @bindings.add("escape", "enter")
        def _(event):
            if draft.placeholder_active:
                event.current_buffer.reset()

        @bindings.add("escape")
        def _(event):
            if draft.placeholder_active:
                event.current_buffer.reset()

        @bindings.add("c-l")
        def _(event):
            event.app.renderer.clear()

        style = Style.from_dict(
            {
                "": "bg:#2b3038 #f2f2f2",
                "prompt": "bg:#2b3038 #5fd7ff bold",
                "bottom-toolbar": "bg:#101820 #8a8f98",
            }
        )
        session = PromptSession(
            FormattedText(_input_prompt_fragments(config, ui_mode, status_text)),
            completer=NyalaCompleter(config.get("workspace", ".")),
            history=history,
            key_bindings=bindings,
            multiline=False,
            wrap_lines=False,
            bottom_toolbar=lambda: _bottom_toolbar(ui_mode, status_text, draft),
            style=style,
            refresh_interval=0.15,
        )
        install_paste_guard(session.default_buffer, draft)
        value = session.prompt()
        was_compacted = draft.has_compacted_submission()
        submission = draft.consume_submission_text(value)
        return submission if was_compacted else submission.strip()
    except (ImportError, EOFError, KeyboardInterrupt):
        raise
    except Exception:
        return input(_fallback_prompt(ui_mode, status_text)).strip()


def _anchor_cursor_bottom() -> None:
    import sys

    if sys.stdout.isatty():
        sys.stdout.write("\033[999B")
        sys.stdout.flush()


def _input_prompt_fragments(config: dict, ui_mode: UiMode, status_text: str):
    return [
        ("class:prompt", "  › "),
    ]


def _bottom_toolbar(ui_mode: UiMode, status_text: str = "", draft: InputDraftState | None = None) -> str:
    hint = " Enter kirim | /quit keluar | Ctrl+C keluar | Ctrl+L bersihkan"
    if draft and draft.placeholder_active:
        hint = " Pasted draft | Enter sends full text | Backspace/Esc clears | Ctrl+C exits"
    if status_text:
        return f"{status_text}  {hint}"
    return hint


def _input_box_lines(ui_mode: UiMode, status_text: str) -> tuple[str, str]:
    width = _box_width(ui_mode)
    if ui_mode.unicode:
        title = _fit_text(f" {status_text or 'Nyala'} ", width - 2, "─", ui_mode)
        return f"╭{title}╮", "│ "
    title = _fit_text(f" {status_text or 'Nyala'} ", width - 2, "-", ui_mode)
    return f"+{title}+", "| "


def _input_box_bottom(ui_mode: UiMode) -> str:
    width = _box_width(ui_mode)
    if ui_mode.unicode:
        return "╰" + "─" * (width - 2) + "╯"
    return "+" + "-" * (width - 2) + "+"


def _continuation_prompt(ui_mode: UiMode) -> str:
    return "│ " if ui_mode.unicode else "| "


def _fallback_prompt(ui_mode: UiMode, status_text: str) -> str:
    return "› "


def _box_width(ui_mode: UiMode) -> int:
    return max(32, min(ui_mode.width, 110))


def _fit_text(text: str, width: int, fill: str, ui_mode: UiMode) -> str:
    if len(text) > width:
        suffix = "…" if ui_mode.unicode else "..."
        text = text[: max(0, width - len(suffix))] + suffix
    return text + fill * max(0, width - len(text))


def ask_text(message: str, default: str = "", password: bool = False) -> str:
    try:
        import questionary

        if password:
            value = questionary.password(message).ask()
        else:
            value = questionary.text(message, default=default).ask()
        return str(value if value is not None else default).strip()
    except Exception:
        if password:
            import getpass

            return getpass.getpass(f"{message}: ").strip()
        suffix = f" [{default}]" if default else ""
        value = input(f"{message}{suffix}: ").strip()
        return value or default


def ask_select(message: str, choices: list[str], default: str | None = None) -> str:
    try:
        import questionary
        from questionary import Style

        style = Style(
            [
                ("qmark", "fg:#00d7ff bold"),
                ("question", "bold"),
                ("answer", "fg:#00d7ff bold"),
                ("pointer", "fg:#00d7ff bold"),
                ("highlighted", "fg:#000000 bg:#00d7ff bold"),
                ("selected", "fg:#00d7ff"),
                ("instruction", "fg:#888888"),
            ]
        )
        value = questionary.select(
            message,
            choices=choices,
            default=default or choices[0],
            pointer="❯",
            style=style,
            use_arrow_keys=True,
        ).ask()
        return str(value or default or choices[0])
    except Exception:
        for idx, item in enumerate(choices, start=1):
            print(f"{idx}. {item}")
        raw = input(f"{message} [1]: ").strip()
        try:
            index = int(raw or "1") - 1
        except ValueError:
            index = 0
        return choices[max(0, min(index, len(choices) - 1))]


def ask_confirm(message: str, default: bool = False) -> bool:
    try:
        import questionary

        return bool(questionary.confirm(message, default=default).ask())
    except Exception:
        suffix = "Y/n" if default else "y/N"
        value = input(f"{message} [{suffix}] ").strip().lower()
        if not value:
            return default
        return value in {"y", "yes", "ya", "iya"}
