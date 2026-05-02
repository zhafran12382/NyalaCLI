from __future__ import annotations

from typing import Any


def compact_history(messages: list[dict[str, Any]], keep_last: int = 8) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create a deterministic memory summary without calling an LLM."""
    older = messages[:-keep_last] if len(messages) > keep_last else []
    recent = messages[-keep_last:] if len(messages) > keep_last else messages

    facts: list[str] = []
    commands: list[str] = []
    files: list[str] = []
    decisions: list[str] = []
    todos: list[str] = []

    for message in older:
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        lowered = content.lower()
        snippet = " ".join(content.split())[:240]
        metadata = message.get("metadata", {}) or {}
        if metadata.get("tool"):
            tool = metadata.get("tool")
            facts.append(f"Tool {tool}: {snippet}")
        elif "todo" in lowered or "lanjut" in lowered:
            todos.append(snippet)
        elif "keputusan" in lowered or "decided" in lowered:
            decisions.append(snippet)
        elif "/" in content or "\\" in content:
            files.append(snippet)
        else:
            facts.append(snippet)
        if metadata.get("command"):
            commands.append(str(metadata["command"]))

    summary = {
        "fakta_penting": _dedupe(facts)[-20:],
        "preferensi_user": [],
        "file_yang_diedit": _dedupe(files)[-20:],
        "command_yang_pernah_dijalankan": _dedupe(commands)[-20:],
        "keputusan_teknis": _dedupe(decisions)[-20:],
        "todo_lanjutan": _dedupe(todos)[-20:],
        "compact_note": f"{len(older)} pesan lama diringkas secara lokal.",
    }
    return summary, recent


def memory_to_prompt(memory: dict[str, Any]) -> str:
    if not memory:
        return "Belum ada compact memory."
    lines = ["Compact memory:"]
    for key, values in memory.items():
        if isinstance(values, list):
            if values:
                lines.append(f"- {key}:")
                lines.extend(f"  - {value}" for value in values)
        else:
            lines.append(f"- {key}: {values}")
    return "\n".join(lines)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
