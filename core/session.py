from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .platform import PlatformInfo, detect_platform, ensure_app_dirs


def new_session_id() -> str:
    return datetime.now(timezone.utc).strftime("nyala-%Y%m%d-%H%M%S")


@dataclass
class Session:
    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_response_tokens: int = 0

    def add(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        self.messages.append(
            {
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "memory": self.memory,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_response_tokens": self.last_response_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(
            session_id=data.get("session_id") or new_session_id(),
            messages=list(data.get("messages", [])),
            memory=dict(data.get("memory", {})),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
            last_response_tokens=int(data.get("last_response_tokens", 0)),
        )


class SessionManager:
    def __init__(self, platform: PlatformInfo | None = None) -> None:
        self.platform = platform or detect_platform()
        ensure_app_dirs(self.platform)
        self.sessions_dir = self.platform.sessions_dir

    def create(self, session_id: str | None = None) -> Session:
        return Session(session_id=session_id or new_session_id())

    def path_for(self, session_id: str) -> Path:
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in ("-", "_"))
        return self.sessions_dir / f"{safe}.json"

    def save(self, session: Session, session_id: str | None = None) -> Path:
        if session_id:
            session.session_id = session_id
        path = self.path_for(session.session_id)
        path.write_text(json.dumps(session.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def load(self, session_id: str) -> Session:
        path = self.path_for(session_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return Session.from_dict(data)

    def exists(self, session_id: str) -> bool:
        return self.path_for(session_id).exists()

    def list_sessions(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for path in sorted(self.sessions_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            result.append(
                {
                    "id": data.get("session_id", path.stem),
                    "messages": len(data.get("messages", [])),
                    "updated_at": data.get("updated_at", ""),
                }
            )
        return result
