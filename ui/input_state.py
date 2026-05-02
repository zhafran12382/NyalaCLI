from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from prompt_toolkit.document import Document


LONG_PASTE_CHAR_THRESHOLD = 300


@dataclass
class InputDraftState:
    raw_value: str = ""
    placeholder_active: bool = False
    placeholder: str = ""
    _submitted_raw_value: str = ""

    def should_compact(self, text: str) -> bool:
        return bool(text) and (len(text) >= LONG_PASTE_CHAR_THRESHOLD or "\n" in text or "\r" in text)

    def activate(self, raw_value: str) -> None:
        self.raw_value = raw_value
        self.placeholder_active = True
        self.placeholder = self._placeholder_for(raw_value)

    def append(self, text: str) -> None:
        if not self.placeholder_active:
            return
        self.raw_value += text
        self.placeholder = self._placeholder_for(self.raw_value)

    def remember_submission(self) -> None:
        if self.placeholder_active:
            self._submitted_raw_value = self.raw_value

    def clear(self, preserve_submission: bool = False) -> None:
        self.raw_value = ""
        self.placeholder_active = False
        self.placeholder = ""
        if not preserve_submission:
            self._submitted_raw_value = ""

    def submission_text(self, display_text: str) -> str:
        if self.placeholder_active:
            return self.raw_value
        if self._submitted_raw_value:
            return self._submitted_raw_value
        return display_text

    def consume_submission_text(self, display_text: str) -> str:
        value = self.submission_text(display_text)
        self._submitted_raw_value = ""
        return value

    def display_text(self, display_text: str) -> str:
        return self.placeholder if self.placeholder_active else display_text

    def status_note(self) -> str:
        return "Draft contains pasted content" if self.placeholder_active else ""

    def has_compacted_submission(self) -> bool:
        return self.placeholder_active or bool(self._submitted_raw_value)

    def _placeholder_for(self, text: str) -> str:
        return f"[Pasted Content ({len(text)} chars)]"


def install_paste_guard(
    buffer: Any,
    draft: InputDraftState,
    on_change: Callable[[], None] | None = None,
) -> None:
    original_insert = buffer.insert_text
    original_delete_before_cursor = buffer.delete_before_cursor
    original_delete = buffer.delete
    original_reset = buffer.reset
    original_set_document = buffer.set_document

    def changed() -> None:
        if on_change:
            on_change()

    def set_display(text: str) -> None:
        original_set_document(Document(text, cursor_position=len(text)), bypass_readonly=True)

    def clear_display() -> None:
        draft.clear()
        original_reset()
        changed()

    def insert_text(data: str, overwrite: bool = False, move_cursor: bool = True, fire_event: bool = True) -> None:
        if draft.placeholder_active:
            draft.append(data)
            set_display(draft.placeholder)
            changed()
            return
        if draft.should_compact(data):
            current = buffer.text
            cursor = buffer.cursor_position
            raw_value = current[:cursor] + data + current[cursor:]
            draft.activate(raw_value)
            set_display(draft.placeholder)
            changed()
            return
        original_insert(data, overwrite=overwrite, move_cursor=move_cursor, fire_event=fire_event)

    def delete_before_cursor(count: int = 1) -> str:
        if draft.placeholder_active:
            removed = draft.placeholder
            clear_display()
            return removed
        return original_delete_before_cursor(count)

    def delete(count: int = 1) -> str:
        if draft.placeholder_active:
            removed = draft.placeholder
            clear_display()
            return removed
        return original_delete(count)

    def reset(document: Document | None = None, append_to_history: bool = False) -> None:
        draft.remember_submission()
        draft.clear(preserve_submission=append_to_history)
        original_reset(document=document, append_to_history=append_to_history)
        changed()

    buffer.insert_text = insert_text
    buffer.delete_before_cursor = delete_before_cursor
    buffer.delete = delete
    buffer.reset = reset
