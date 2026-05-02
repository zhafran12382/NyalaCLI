from __future__ import annotations

from pathlib import Path

from core.platform import PlatformInfo
from core.session import SessionManager


def make_platform(tmp_path: Path) -> PlatformInfo:
    return PlatformInfo(
        system="Linux",
        is_termux=False,
        home=tmp_path,
        config_dir=tmp_path / ".nyalacli",
        env_file=tmp_path / ".nyalacli" / ".env",
        sessions_dir=tmp_path / ".nyalacli" / "sessions",
        logs_dir=tmp_path / ".nyalacli" / "logs",
        cache_dir=tmp_path / ".nyalacli" / "cache",
        default_workspace=tmp_path / "workspace",
        storage_shared=tmp_path / "storage" / "shared",
        storage_accessible=False,
        shell_hint="sh",
    )


def test_session_save_load(tmp_path: Path) -> None:
    manager = SessionManager(make_platform(tmp_path))
    session = manager.create("abc")
    session.add("user", "halo")
    manager.save(session)
    loaded = manager.load("abc")
    assert loaded.session_id == "abc"
    assert loaded.messages[0]["content"] == "halo"
