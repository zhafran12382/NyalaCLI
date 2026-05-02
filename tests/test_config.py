from __future__ import annotations

from pathlib import Path

from core.config import ConfigManager
from core.platform import PlatformInfo


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


def test_config_default_workspace(tmp_path: Path) -> None:
    manager = ConfigManager(make_platform(tmp_path))
    config = manager.load()
    assert config["workspace"] == str(tmp_path / "workspace")
    assert config["safety_mode"] == "safe"


def test_env_write_and_status(tmp_path: Path, monkeypatch) -> None:
    manager = ConfigManager(make_platform(tmp_path))
    manager.write_env({"OPENROUTER_API_KEY": "sk-or-v1-test"})
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    assert manager.secret_status()["openrouter"] is True
