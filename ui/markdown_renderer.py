from __future__ import annotations

import io
import re
from dataclasses import dataclass

from rich.console import Console, Group
from rich.markdown import CodeBlock, Markdown
from rich.padding import Padding
from rich.syntax import Syntax
from rich.text import Text

from .theme import NYALA_THEME, UiMode


EMPTY_RESPONSE = "(kosong)"
STYLE_MARK = "\uE000"
STYLE_END = "\uE001"

_LINE_MARK_PREFIX = f"{STYLE_MARK}@"
_INLINE_STYLE_CODES = {"B", "I", "C", "L", "U"}
_MOJIBAKE_REPLACEMENTS = {
    "â<86><92>": "→",
    "â<80><93>": "–",
    "â<80><94>": "—",
    "â<80><98>": "‘",
    "â<80><99>": "’",
    "â<80><9C>": "“",
    "â<80><9D>": "”",
    "â<80><A6>": "…",
    "â\x86\x92": "→",
    "â\x80\x93": "–",
    "â\x80\x94": "—",
    "â\x80\x98": "‘",
    "â\x80\x99": "’",
    "â\x80\x9c": "“",
    "â\x80\x9d": "”",
    "â\x80¦": "…",
    "â†’": "→",
    "â€“": "–",
    "â€”": "—",
    "â€˜": "‘",
    "â€™": "’",
    "â€œ": "“",
    "â€": "”",
    "â€¦": "…",
    "Â·": "·",
    "Â ": " ",
}
_ASCII_FALLBACKS = str.maketrans(
    {
        "→": "->",
        "←": "<-",
        "–": "-",
        "—": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        "•": "-",
        "▌": ">",
        "▸": ">",
    }
)


@dataclass(frozen=True)
class _ListState:
    ordered: bool
    marker: str


class NyalaCodeBlock(CodeBlock):
    def __rich_console__(self, console: Console, options):
        if console.color_system is None:
            code = str(self.text).rstrip("\n")
            language = self.lexer_name if self.lexer_name and self.lexer_name != "text" else "code"
            width = max(16, min(options.max_width, max([len(line) for line in code.splitlines()] + [len(language) + 8]) + 4))
            title = f" {language} "
            rule = _code_rule(title, width)
            yield Text(rule, style="markdown.code_block")
            for line in code.splitlines() or [""]:
                yield Text(f"  {line}", style="markdown.code")
            yield Text("─" * width, style="markdown.code_block")
            return
        syntax = Syntax(str(self.text).rstrip(), self.lexer_name, theme=self.theme, word_wrap=True, padding=1)
        yield syntax


class NyalaMarkdown(Markdown):
    elements = {
        **Markdown.elements,
        "fence": NyalaCodeBlock,
        "code_block": NyalaCodeBlock,
    }


def markdown_renderable(text: str) -> Markdown:
    """Return the shared Rich Markdown renderer for assistant output."""
    return NyalaMarkdown(
        normalize_terminal_text(text) or EMPTY_RESPONSE,
        code_theme="monokai",
        hyperlinks=True,
        inline_code_theme="monokai",
    )


def assistant_response_renderable(text: str, ui_mode: UiMode) -> Group:
    label = Text()
    label.append("Nyala", style="nyala.ai")
    return Group(label, Padding(markdown_renderable(text), (0, 0, 1, 2)))


def render_markdown_text(text: str, width: int, ui_mode: UiMode) -> str:
    """Render Markdown to clean wrapped text for the prompt_toolkit transcript."""
    return _PromptMarkdownRenderer(width, ui_mode, styled=False).render(normalize_terminal_text(text, ui_mode) or EMPTY_RESPONSE)


def guided_assistant_text(text: str, width: int, ui_mode: UiMode) -> str:
    body_width = max(24, width - 6)
    rendered = _PromptMarkdownRenderer(body_width, ui_mode, styled=True).render(normalize_terminal_text(text, ui_mode) or EMPTY_RESPONSE)
    guide = "│" if ui_mode.unicode else "|"
    return "\n".join(f"  {guide} {line}" if line else f"  {guide}" for line in rendered.splitlines())


def assistant_transcript_text(text: str, width: int, ui_mode: UiMode) -> str:
    """Render assistant Markdown without visible chat rails or bordered bubbles."""
    body_width = max(24, width - 4)
    rendered = _PromptMarkdownRenderer(body_width, ui_mode, styled=True).render(normalize_terminal_text(text, ui_mode) or EMPTY_RESPONSE)
    return "\n".join(f"  {line}" if line else "  " for line in rendered.splitlines())


def normalize_terminal_text(text: str, ui_mode: UiMode | None = None) -> str:
    repaired = _repair_mojibake(str(text or ""))
    if ui_mode and not ui_mode.unicode:
        repaired = _ascii_fallback(repaired)
    return repaired


def strip_style_markers(text: str) -> str:
    """Remove hidden transcript style markers from rendered Markdown text."""
    out: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == STYLE_MARK:
            if text.startswith(_LINE_MARK_PREFIX, i):
                end = text.find(STYLE_END, i)
                i = len(text) if end == -1 else end + 1
                continue
            if i + 1 < len(text) and text[i + 1] in _INLINE_STYLE_CODES:
                i += 2
                continue
        if char == STYLE_END:
            i += 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


def split_line_style(text: str) -> tuple[str | None, str]:
    if not text.startswith(_LINE_MARK_PREFIX):
        return None, text
    end = text.find(STYLE_END, len(_LINE_MARK_PREFIX))
    if end == -1:
        return None, text
    return text[len(_LINE_MARK_PREFIX) : end], text[end + 1 :]


class _PromptMarkdownRenderer:
    def __init__(self, width: int, ui_mode: UiMode, styled: bool) -> None:
        from markdown_it import MarkdownIt

        self.width = max(24, width)
        self.ui_mode = ui_mode
        self.styled = styled
        self.parser = MarkdownIt().enable("strikethrough").enable("table")

    def render(self, text: str) -> str:
        tokens = self.parser.parse(text or EMPTY_RESPONSE)
        lines, _ = self._blocks(tokens, 0, set())
        lines = self._clean_blank_lines(lines)
        return "\n".join(lines).strip("\n") or EMPTY_RESPONSE

    def _blocks(self, tokens, index: int, stop: set[str]) -> tuple[list[str], int]:
        lines: list[str] = []
        while index < len(tokens):
            token = tokens[index]
            if token.type in stop:
                break
            block: list[str] = []

            if token.type == "heading_open":
                level = int(token.tag[1:]) if token.tag.startswith("h") and token.tag[1:].isdigit() else 2
                inline = tokens[index + 1] if index + 1 < len(tokens) else None
                block = self._heading(level, self._inline(inline.children if inline and inline.children else []))
                index += 3
            elif token.type == "paragraph_open":
                inline = tokens[index + 1] if index + 1 < len(tokens) else None
                block = self._paragraph(self._inline(inline.children if inline and inline.children else []))
                index += 3
            elif token.type in {"fence", "code_block"}:
                block = self._code_block(token.content, token.info)
                index += 1
            elif token.type == "hr":
                block = [self._line("HR", self._rule(self.width))]
                index += 1
            elif token.type == "blockquote_open":
                inner, index = self._blocks(tokens, index + 1, {"blockquote_close"})
                if index < len(tokens) and tokens[index].type == "blockquote_close":
                    index += 1
                block = self._blockquote(inner)
            elif token.type == "bullet_list_open":
                block, index = self._list(tokens, index, _ListState(False, ""))
            elif token.type == "ordered_list_open":
                start = int(token.attrs.get("start", "1")) if token.attrs else 1
                block, index = self._list(tokens, index, _ListState(True, str(start)))
            elif token.type == "table_open":
                block, index = self._table(tokens, index + 1)
            elif token.type == "inline":
                block = self._paragraph(self._inline(token.children or []))
                index += 1
            else:
                index += 1

            self._append_block(lines, block)
        return lines, index

    def _heading(self, level: int, text: str) -> list[str]:
        if level == 1:
            prefix = "━━ " if self.ui_mode.unicode else "== "
            style = "H1"
        elif level == 2:
            prefix = "── " if self.ui_mode.unicode else "-- "
            style = "H2"
        else:
            prefix = "▸ " if self.ui_mode.unicode else "> "
            style = "H3"
        return [self._line(style, line) for line in self._wrap(text, self.width, prefix, " " * _visible_width(prefix))]

    def _paragraph(self, text: str) -> list[str]:
        return [self._line("P", line) for line in self._wrap(text, self.width)]

    def _code_block(self, code: str, info: str) -> list[str]:
        language = (info or "").strip().split(maxsplit=1)[0] or "code"
        title = f" {language} "
        lines = [self._line("CODE_BORDER", _code_rule(title, min(self.width, max(18, _longest_line(code) + 4)), self.ui_mode))]
        for raw_line in code.rstrip("\n").splitlines() or [""]:
            expanded = raw_line.expandtabs(4)
            wrapped = _wrap_plain(expanded, max(12, self.width - 4))
            for part in wrapped or [""]:
                lines.append(self._line("CODE", f"  {part}"))
        lines.append(self._line("CODE_BORDER", self._rule(min(self.width, max(18, _longest_line(code) + 4)))))
        return lines

    def _blockquote(self, inner: list[str]) -> list[str]:
        prefix = "▌ " if self.ui_mode.unicode else "> "
        lines: list[str] = []
        for line in self._trim_blank(inner):
            _style, content = split_line_style(line)
            lines.append(self._line("QUOTE", prefix + content if content else prefix.rstrip()))
        return lines

    def _list(self, tokens, index: int, state: _ListState) -> tuple[list[str], int]:
        close = "ordered_list_close" if state.ordered else "bullet_list_close"
        number = int(state.marker or "1")
        marker = "•" if self.ui_mode.unicode else "-"
        lines: list[str] = []
        index += 1
        while index < len(tokens) and tokens[index].type != close:
            if tokens[index].type != "list_item_open":
                index += 1
                continue
            inner, index = self._blocks(tokens, index + 1, {"list_item_close"})
            if index < len(tokens) and tokens[index].type == "list_item_close":
                index += 1
            marker_text = f"{number}. " if state.ordered else f"{marker} "
            lines.extend(self._list_item(self._trim_blank(inner), marker_text))
            number += 1
        if index < len(tokens) and tokens[index].type == close:
            index += 1
        return lines, index

    def _list_item(self, inner: list[str], marker: str) -> list[str]:
        if not inner:
            return [self._line("LIST", marker.rstrip())]
        indent = " " * _visible_width(marker)
        lines: list[str] = []
        first = True
        for line in inner:
            style, content = split_line_style(line)
            line_style = style if style in {"CODE", "CODE_BORDER", "QUOTE"} else "LIST"
            if not content:
                lines.append("")
                continue
            prefix = marker if first else indent
            lines.append(self._line(line_style, prefix + content))
            first = False
        return lines

    def _table(self, tokens, index: int) -> tuple[list[str], int]:
        rows: list[list[str]] = []
        row: list[str] | None = None
        cell_parts: list[str] | None = None
        while index < len(tokens) and tokens[index].type != "table_close":
            token = tokens[index]
            if token.type == "tr_open":
                row = []
            elif token.type in {"th_open", "td_open"}:
                cell_parts = []
            elif token.type == "inline" and cell_parts is not None:
                cell_parts.append(strip_style_markers(self._inline(token.children or [])))
            elif token.type in {"th_close", "td_close"} and row is not None:
                row.append(" ".join(cell_parts or []).strip())
                cell_parts = None
            elif token.type == "tr_close" and row is not None:
                rows.append(row)
                row = None
            index += 1
        if index < len(tokens) and tokens[index].type == "table_close":
            index += 1
        return self._format_table(rows), index

    def _format_table(self, rows: list[list[str]]) -> list[str]:
        if not rows:
            return []
        columns = max(len(row) for row in rows)
        normalized = [row + [""] * (columns - len(row)) for row in rows]
        widths = [max(3, max(len(row[col]) for row in normalized)) for col in range(columns)]
        separator = " │ " if self.ui_mode.unicode else " | "
        max_content = max(columns * 3, self.width - len(separator) * (columns - 1))
        while sum(widths) > max_content and max(widths) > 4:
            largest = max(range(columns), key=lambda col: widths[col])
            widths[largest] -= 1

        def row_text(row: list[str]) -> str:
            cells = [_clip(row[col], widths[col]).ljust(widths[col]) for col in range(columns)]
            return separator.join(cells).rstrip()

        joiner = "─┼─" if self.ui_mode.unicode else "-+-"
        rule = joiner.join("─" * width if self.ui_mode.unicode else "-" * width for width in widths)
        lines = [self._line("TABLE_HEADER", row_text(normalized[0])), self._line("TABLE_BORDER", rule)]
        for row in normalized[1:]:
            lines.append(self._line("TABLE", row_text(row)))
        return lines

    def _inline(self, children) -> str:
        out: list[str] = []
        links: list[str] = []
        for child in children or []:
            kind = child.type
            if kind == "text":
                out.append(child.content)
            elif kind == "softbreak":
                out.append(" ")
            elif kind == "hardbreak":
                out.append("\n")
            elif kind == "code_inline":
                out.append(self._inline_style("C", child.content, fallback=f"`{child.content}`"))
            elif kind == "strong_open":
                out.append(self._start("B"))
            elif kind == "strong_close":
                out.append(self._end())
            elif kind == "em_open":
                out.append(self._start("I"))
            elif kind == "em_close":
                out.append(self._end())
            elif kind == "s_open":
                out.append(self._start("U"))
            elif kind == "s_close":
                out.append(self._end())
            elif kind == "link_open":
                href = str(child.attrs.get("href", "")) if child.attrs else ""
                links.append(href)
                out.append(self._start("L"))
            elif kind == "link_close":
                out.append(self._end())
                href = links.pop() if links else ""
                if href:
                    out.append(" ")
                    out.append(self._inline_style("L", f"({href})", fallback=f"({href})"))
            elif kind == "image":
                alt = child.content or "image"
                src = str(child.attrs.get("src", "")) if child.attrs else ""
                out.append(f"[image: {alt}]")
                if src:
                    out.append(f" ({src})")
            elif kind == "html_inline" and child.content in {"<kbd>", "</kbd>"}:
                out.append(self._start("C") if child.content == "<kbd>" else self._end())
            elif child.children:
                out.append(self._inline(child.children))
        return "".join(out)

    def _inline_style(self, style: str, text: str, fallback: str) -> str:
        return f"{self._start(style)}{text}{self._end()}" if self.styled else fallback

    def _start(self, style: str) -> str:
        return f"{STYLE_MARK}{style}" if self.styled else ""

    def _end(self) -> str:
        return STYLE_END if self.styled else ""

    def _line(self, style: str, text: str) -> str:
        return f"{_LINE_MARK_PREFIX}{style}{STYLE_END}{text}" if self.styled else text

    def _wrap(self, text: str, width: int, initial_indent: str = "", subsequent_indent: str = "") -> list[str]:
        wrapped: list[str] = []
        for part in text.split("\n"):
            wrapped.extend(_wrap_marked(part, width, initial_indent, subsequent_indent))
            initial_indent = subsequent_indent
        return wrapped or [""]

    def _rule(self, width: int) -> str:
        return ("─" if self.ui_mode.unicode else "-") * max(8, min(width, self.width))

    @staticmethod
    def _append_block(lines: list[str], block: list[str]) -> None:
        block = _PromptMarkdownRenderer._trim_blank(block)
        if not block:
            return
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(block)
        lines.append("")

    @staticmethod
    def _trim_blank(lines: list[str]) -> list[str]:
        while lines and not strip_style_markers(lines[0]).strip():
            lines.pop(0)
        while lines and not strip_style_markers(lines[-1]).strip():
            lines.pop()
        return lines

    @staticmethod
    def _clean_blank_lines(lines: list[str]) -> list[str]:
        clean: list[str] = []
        blank = False
        for line in lines:
            is_blank = not strip_style_markers(line).strip()
            if is_blank and blank:
                continue
            clean.append("" if is_blank else line.rstrip())
            blank = is_blank
        return _PromptMarkdownRenderer._trim_blank(clean)


def _rstrip_lines(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines())


def _code_rule(title: str, width: int, ui_mode: UiMode | None = None) -> str:
    label = f" {title.strip()} "
    if len(label) >= width:
        return label[:width]
    right = width - len(label) - 1
    rule = "─" if ui_mode is None or ui_mode.unicode else "-"
    return rule + label + rule * max(0, right)


def _wrap_marked(text: str, width: int, initial_indent: str = "", subsequent_indent: str = "") -> list[str]:
    text = text.strip()
    if not text:
        return [initial_indent.rstrip()] if initial_indent else [""]
    parts = [part for part in re.split(r"(\s+)", text) if part]
    lines: list[str] = []
    current = initial_indent
    current_width = _visible_width(current)
    pending_space = ""
    for part in parts:
        if part.isspace():
            pending_space = " "
            continue
        addition = (pending_space if strip_style_markers(current).strip() else "") + part
        addition_width = _visible_width(addition)
        if strip_style_markers(current).strip() and current_width + addition_width > width:
            lines.append(current.rstrip())
            current = subsequent_indent + part
            current_width = _visible_width(current)
        else:
            current += addition
            current_width += addition_width
        pending_space = ""
    if current or not lines:
        lines.append(current.rstrip())
    return lines


def _wrap_plain(text: str, width: int) -> list[str]:
    if len(text) <= width:
        return [text]
    lines: list[str] = []
    remaining = text
    while len(remaining) > width:
        lines.append(remaining[:width])
        remaining = remaining[width:]
    lines.append(remaining)
    return lines


def _visible_width(text: str) -> int:
    return len(strip_style_markers(text))


def _longest_line(text: str) -> int:
    return max([len(line.expandtabs(4)) for line in text.splitlines()] + [0])


def _clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _repair_mojibake(text: str) -> str:
    repaired = text
    for bad, good in _MOJIBAKE_REPLACEMENTS.items():
        repaired = repaired.replace(bad, good)
    if not _looks_like_mojibake(repaired):
        return repaired
    for encoding in ("cp1252", "latin-1"):
        try:
            candidate = repaired.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if _mojibake_score(candidate) < _mojibake_score(repaired):
            repaired = candidate
            break
    for bad, good in _MOJIBAKE_REPLACEMENTS.items():
        repaired = repaired.replace(bad, good)
    return repaired


def _looks_like_mojibake(text: str) -> bool:
    if "Ã" in text or "Â" in text:
        return True
    return bool(re.search(r"â(?:[\x80-\xBF]|[†€™€œ€�€“€”€¦]|<80>|<86>)", text))


def _mojibake_score(text: str) -> int:
    return sum(text.count(marker) for marker in ("Ã", "Â", "â", "<80>", "<86>", "�"))


def _ascii_fallback(text: str) -> str:
    return text.translate(_ASCII_FALLBACKS)
