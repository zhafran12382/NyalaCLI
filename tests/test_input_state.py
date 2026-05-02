from __future__ import annotations

from prompt_toolkit.buffer import Buffer

from ui.input_state import InputDraftState, install_paste_guard


def test_long_paste_uses_placeholder_but_submits_raw_text() -> None:
    buffer = Buffer(multiline=False)
    draft = InputDraftState()
    install_paste_guard(buffer, draft)
    pasted = "alpha\n" + "x" * 400

    buffer.insert_text(pasted)

    assert buffer.text == f"[Pasted Content ({len(pasted)} chars)]"
    assert draft.submission_text(buffer.text) == pasted


def test_typing_after_long_paste_appends_to_raw_draft() -> None:
    buffer = Buffer(multiline=False)
    draft = InputDraftState()
    install_paste_guard(buffer, draft)
    pasted = "x" * 350

    buffer.insert_text(pasted)
    buffer.insert_text(" suffix")

    assert buffer.text == f"[Pasted Content ({len(pasted) + 7} chars)]"
    assert draft.submission_text(buffer.text) == pasted + " suffix"


def test_deleting_placeholder_clears_raw_draft() -> None:
    buffer = Buffer(multiline=False)
    draft = InputDraftState()
    install_paste_guard(buffer, draft)

    buffer.insert_text("x" * 350)
    buffer.delete_before_cursor()

    assert buffer.text == ""
    assert draft.submission_text(buffer.text) == ""
