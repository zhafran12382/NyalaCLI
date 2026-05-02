from __future__ import annotations

from ui.markdown_renderer import assistant_transcript_text, guided_assistant_text, normalize_terminal_text, render_markdown_text, strip_style_markers
from ui.theme import UiMode


def test_markdown_renderer_formats_common_blocks() -> None:
    markdown = """# Heading

Some **bold** and *italic* with `code` plus [docs](https://example.com).

- alpha
- beta

1. one
2. two

> quoted text

---

```python
print("hi")
```

| A | B |
|---|---|
| 1 | 2 |
"""

    rendered = render_markdown_text(markdown, 72, UiMode(True, False, 80, 24))

    assert "━━ Heading" in rendered
    assert "Some bold and italic with `code` plus docs (https://example.com)." in rendered
    assert "• alpha" in rendered
    assert "1. one" in rendered
    assert "▌ quoted text" in rendered
    assert "python" in rendered
    assert 'print("hi")' in rendered
    assert "A" in rendered and "B" in rendered and "1" in rendered and "2" in rendered
    assert "**bold**" not in rendered


def test_guided_assistant_text_wraps_without_chat_box() -> None:
    rendered = strip_style_markers(
        guided_assistant_text("A paragraph with **emphasis** and `inline code`.", 64, UiMode(True, False, 80, 24))
    )

    assert rendered.startswith("  │ A paragraph")
    assert "╭" not in rendered
    assert "╰" not in rendered
    assert "│ A paragraph" in rendered


def test_assistant_transcript_text_has_no_visible_chat_rail() -> None:
    rendered = strip_style_markers(
        assistant_transcript_text("Ringkasan **berita** dengan `code`.", 64, UiMode(True, False, 80, 24))
    )

    assert rendered.startswith("  Ringkasan")
    assert "  │" not in rendered
    assert "◆" not in rendered
    assert "berita" in rendered


def test_terminal_text_repairs_common_mojibake() -> None:
    text = normalize_terminal_text("Demo May Day â<86><92> kebijakan driver online â€™ aman.", UiMode(True, False, 80, 24))

    assert "→" in text
    assert "’" in text
    assert "â<86><92>" not in text
