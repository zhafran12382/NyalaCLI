from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class SkillResult:
    ok: bool
    output: str
    full_output: str | None = None
    metadata: dict[str, Any] | None = None


class BaseSkill(Protocol):
    name: str
    description: str
    parameters_schema: dict[str, Any]

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
        ...


def workspace_path(workspace: str | Path, value: str | None = None) -> Path:
    base = Path(workspace).expanduser()
    if not value:
        return base.resolve()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def truncate(text: str, max_length: int = 6000) -> tuple[str, bool]:
    if len(text) <= max_length:
        return text, False
    return text[:max_length] + f"\n\n[truncated {len(text) - max_length} chars]", True
