from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .platform import PlatformInfo, detect_platform, ensure_app_dirs
from .provider_catalog import PROVIDER_OPTIONS


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "provider": "openrouter",
    "model": "openrouter/free",
    "base_url": "http://127.0.0.1:1234/v1",
    "routing": "",
    "custom_provider_name": "Custom OpenAI-compatible",
    "thinking_effort": "",
    "temperature": 0.4,
    "max_tokens": 2048,
    "stream": False,
    "safety_mode": "balanced",
    "workspace": "",
    "debug": False,
    "ui": {
        "unicode": "auto",
        "compact": "auto",
        "clear_on_start": True,
        "show_spinner": True,
    },
    "team": {
        "planners": 1,
        "runners": 2,
        "roles": ["coder", "researcher"],
    },
}


SECRET_ENV_KEYS = {
    key: option.api_key_env
    for key, option in PROVIDER_OPTIONS.items()
    if option.api_key_env
}
SECRET_ENV_KEYS["tavily"] = "TAVILY_API_KEY"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigManager:
    def __init__(self, platform: PlatformInfo | None = None, config_path: Path | None = None) -> None:
        self.platform = platform or detect_platform()
        self.config_path = config_path or (self.platform.config_dir / "config.json")
        self.env_path = self.platform.env_file

    def ensure(self) -> None:
        ensure_app_dirs(self.platform)
        if not self.config_path.exists():
            config = deepcopy(DEFAULT_CONFIG)
            config["safety_mode"] = "balanced" if self.platform.is_termux else "safe"
            config["workspace"] = str(self.platform.default_workspace)
            self.save(config)
        if not self.env_path.exists():
            self.env_path.touch(mode=0o600, exist_ok=True)

    def load(self) -> dict[str, Any]:
        self.ensure()
        load_dotenv(self.env_path, override=False)
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        config = deep_merge(DEFAULT_CONFIG, data)
        if not config.get("workspace"):
            config["workspace"] = str(self.platform.default_workspace)
        return config

    def save(self, config: dict[str, Any]) -> None:
        ensure_app_dirs(self.platform)
        self.config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        try:
            self.config_path.chmod(0o600)
        except OSError:
            pass

    def update(self, **changes: Any) -> dict[str, Any]:
        config = self.load()
        config.update(changes)
        self.save(config)
        return config

    def write_env(self, values: dict[str, str]) -> None:
        ensure_app_dirs(self.platform)
        existing = self.read_env_file()
        for key, value in values.items():
            if value:
                existing[key] = value
        lines = [f"{key}={_quote_env(value)}" for key, value in sorted(existing.items())]
        self.env_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        try:
            self.env_path.chmod(0o600)
        except OSError:
            pass
        load_dotenv(self.env_path, override=True)

    def read_env_file(self) -> dict[str, str]:
        if not self.env_path.exists():
            return {}
        result: dict[str, str] = {}
        for raw in self.env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
        return result

    def secret_status(self) -> dict[str, bool]:
        load_dotenv(self.env_path, override=False)
        return {key: bool(os.environ.get(env_key)) for key, env_key in SECRET_ENV_KEYS.items()}

    def redacted_summary(self) -> dict[str, Any]:
        config = self.load()
        summary = {
            "provider": config.get("provider"),
            "model": config.get("model"),
            "base_url": config.get("base_url"),
            "routing": config.get("routing") or "auto",
            "thinking_effort": config.get("thinking_effort") or "off",
            "custom_provider_name": config.get("custom_provider_name"),
            "stream": bool(config.get("stream", False)),
            "safety_mode": config.get("safety_mode"),
            "workspace": config.get("workspace"),
            "secrets": self.secret_status(),
        }
        return summary


def _quote_env(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
