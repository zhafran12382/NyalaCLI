from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .permissions import is_sensitive_file, safe_path_display


MENTION_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9._/\-]+)")
MAX_ATTACHMENTS = 5
MAX_FILE_CHARS = 12000
MAX_TOTAL_CHARS = 30000


@dataclass(frozen=True)
class PromptAttachment:
    mention: str
    path: Path | None
    included: bool
    reason: str = ""
    chars: int = 0


def build_file_context(user_text: str, workspace: str | Path) -> tuple[str, list[PromptAttachment]]:
    root = Path(workspace).expanduser().resolve()
    seen: set[str] = set()
    attachments: list[PromptAttachment] = []
    context_blocks: list[str] = []
    total_chars = 0

    for raw in MENTION_RE.findall(user_text):
        if raw in seen:
            continue
        seen.add(raw)
        if len([item for item in attachments if item.included]) >= MAX_ATTACHMENTS:
            attachments.append(PromptAttachment(raw, None, False, "attachment limit reached"))
            continue

        target = _resolve_mention(root, raw)
        if target is None:
            attachments.append(PromptAttachment(raw, None, False, "outside workspace"))
            continue
        if is_sensitive_file(target):
            attachments.append(PromptAttachment(raw, target, False, "sensitive file"))
            continue
        if not target.exists():
            attachments.append(PromptAttachment(raw, target, False, "not found"))
            continue
        if not target.is_file():
            attachments.append(PromptAttachment(raw, target, False, "not a file"))
            continue

        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            attachments.append(PromptAttachment(raw, target, False, f"read error: {exc}"))
            continue

        remaining = MAX_TOTAL_CHARS - total_chars
        if remaining <= 0:
            attachments.append(PromptAttachment(raw, target, False, "context budget reached"))
            continue
        clipped = text[: min(MAX_FILE_CHARS, remaining)]
        total_chars += len(clipped)
        if len(clipped) < len(text):
            clipped += "\n[truncated]"
        language = _language_for(target)
        label = safe_path_display(target)
        context_blocks.append(f"--- @{raw} ({label}) ---\n```{language}\n{clipped}\n```")
        attachments.append(PromptAttachment(raw, target, True, chars=len(clipped)))

    if not context_blocks:
        return "", attachments
    header = "User explicitly attached these workspace files with @file mentions. Use them as local context:"
    return header + "\n\n" + "\n\n".join(context_blocks), attachments


def attachment_notice(attachments: list[PromptAttachment]) -> str:
    if not attachments:
        return ""
    lines = []
    for item in attachments:
        if item.included:
            path = safe_path_display(item.path) if item.path else item.mention
            lines.append(f"attached @{item.mention} -> {path} ({item.chars} chars)")
        else:
            lines.append(f"skipped @{item.mention}: {item.reason}")
    return "\n".join(lines)


def _resolve_mention(root: Path, raw: str) -> Path | None:
    path = Path(raw)
    target = path.expanduser().resolve() if path.is_absolute() else (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def _language_for(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "tsx": "tsx",
        "json": "json",
        "md": "markdown",
        "sh": "sh",
        "toml": "toml",
        "yaml": "yaml",
        "yml": "yaml",
    }.get(suffix, "")
