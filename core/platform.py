from __future__ import annotations

import os
import platform as py_platform
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformInfo:
    system: str
    is_termux: bool
    home: Path
    config_dir: Path
    env_file: Path
    sessions_dir: Path
    logs_dir: Path
    cache_dir: Path
    default_workspace: Path
    storage_shared: Path
    storage_accessible: bool
    shell_hint: str

    @property
    def label(self) -> str:
        if self.is_termux:
            return "Termux Android"
        if self.system == "Darwin":
            return "macOS"
        if self.system == "Windows":
            return "Windows"
        return self.system or "Unknown"


def is_termux_environment() -> bool:
    prefix = os.environ.get("PREFIX", "")
    home = str(Path.home())
    checks = [
        "com.termux" in prefix,
        prefix.startswith("/data/data/com.termux"),
        home.startswith("/data/data/com.termux"),
        Path("/data/data/com.termux").exists(),
    ]
    return any(checks)


def detect_platform() -> PlatformInfo:
    home = Path.home()
    config_dir = home / ".nyalacli"
    storage_shared = home / "storage" / "shared"
    storage_accessible = storage_shared.exists() and os.access(storage_shared, os.W_OK)
    is_termux = is_termux_environment()

    if is_termux and storage_accessible:
        default_workspace = storage_shared / "NyalaCLI"
    else:
        default_workspace = home / "NyalaCLI_Workspace"

    system = py_platform.system()
    shell_hint = "powershell" if system == "Windows" else os.environ.get("SHELL", "sh")

    return PlatformInfo(
        system=system,
        is_termux=is_termux,
        home=home,
        config_dir=config_dir,
        env_file=config_dir / ".env",
        sessions_dir=config_dir / "sessions",
        logs_dir=config_dir / "logs",
        cache_dir=config_dir / "cache",
        default_workspace=default_workspace,
        storage_shared=storage_shared,
        storage_accessible=storage_accessible,
        shell_hint=shell_hint,
    )


def ensure_app_dirs(info: PlatformInfo) -> None:
    for path in [info.config_dir, info.sessions_dir, info.logs_dir, info.cache_dir]:
        path.mkdir(parents=True, exist_ok=True)
    info.default_workspace.mkdir(parents=True, exist_ok=True)


def terminal_supports_unicode() -> bool:
    encoding = os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE") or ""
    term = os.environ.get("TERM", "")
    if "UTF-8" in encoding.upper() or "UTF8" in encoding.upper():
        return True
    if term and term.lower() != "dumb":
        return True
    return os.name != "nt"
