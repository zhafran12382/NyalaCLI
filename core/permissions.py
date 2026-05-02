from __future__ import annotations

import fnmatch
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SENSITIVE_PATTERNS = [
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "token.json",
    "*.pem",
    "*.key",
    "known_hosts",
    "*password*",
    "passwd",
    "shadow",
]

EXTREME_BLOCK_PATTERNS = [
    r"rm\s+-[^&;\n]*r[^&;\n]*f[^&;\n]*\s+/",
    r"rm\s+-[^&;\n]*r[^&;\n]*f[^&;\n]*\s+~(\s|$|/)",
    r"rm\s+-[^&;\n]*r[^&;\n]*f[^&;\n]*\s+\$HOME(\s|$|/)",
    r"rm\s+-[^&;\n]*r[^&;\n]*f[^&;\n]*\s+/data(\s|$|/)",
    r"rm\s+-[^&;\n]*r[^&;\n]*f[^&;\n]*\s+/sdcard(\s|$|/)",
    r"rm\s+-[^&;\n]*r[^&;\n]*f[^&;\n]*\s+~/storage(\s|$|/)",
    r":\(\)\{\s*:\|:&\s*\};:",
    r"\bmkfs(\.|\s|$)",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"chmod\s+-R\s+777\s+/",
    r"chmod\s+-R\s+777\s+~",
    r"\bchown\s+-R\b",
    r"\bcurl\b.*\|\s*(bash|sh)",
    r"\bwget\b.*\|\s*(bash|sh)",
]

RISKY_PATTERNS = [
    r"\brm\b",
    r"\bmv\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\bpkg\s+install\b",
    r"\bapt\s+install\b",
    r"\bpip\s+install\b",
    r"\bcurl\b.*\|\s*(bash|sh)",
    r"\bwget\b.*\|\s*(bash|sh)",
    r"\bpython3?\s+-c\b.*(remove|unlink|rmtree)",
]

READ_ONLY_COMMANDS = {
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "sed",
    "awk",
    "grep",
    "rg",
    "find",
    "wc",
    "git",
    "python",
    "python3",
    "pip",
    "pip3",
    "curl",
}

SECRET_REGEXES = [
    re.compile(r"(sk-or-v1-[A-Za-z0-9_\-]{12,})"),
    re.compile(r"(AIza[0-9A-Za-z_\-]{20,})"),
    re.compile(r"(tvly-[A-Za-z0-9_\-]{12,})"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{12,}", re.IGNORECASE),
    re.compile(r"([A-Z0-9_]*API[_-]?KEY[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9_\-./]{8,}", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]


@dataclass
class PermissionDecision:
    allowed: bool
    reason: str = ""
    requires_confirmation: bool = False


class PermissionManager:
    def __init__(self, safety_mode: str = "balanced", interactive: bool = True) -> None:
        self.safety_mode = safety_mode if safety_mode in {"safe", "balanced", "freedom"} else "balanced"
        self.interactive = interactive

    def check_command(self, command: str) -> PermissionDecision:
        stripped = command.strip()
        if not stripped:
            return PermissionDecision(False, "Command kosong.")
        if is_extreme_command(stripped):
            return PermissionDecision(False, "Command diblokir karena terlalu destruktif.")
        if self.safety_mode == "safe":
            return PermissionDecision(True, "Mode safe meminta konfirmasi semua bash command.", True)
        if is_risky_command(stripped):
            return PermissionDecision(True, "Command berisiko dan perlu konfirmasi.", True)
        if self.safety_mode == "balanced" and not is_read_only_command(stripped):
            return PermissionDecision(True, "Command bukan read-only yang jelas, perlu konfirmasi.", True)
        return PermissionDecision(True)

    def check_python_code(self, code: str) -> PermissionDecision:
        lowered = code.lower()
        risky = any(token in lowered for token in ["shutil.rmtree", "os.remove", "unlink(", "rm -rf", "subprocess"])
        if risky and self.safety_mode != "freedom":
            return PermissionDecision(True, "Kode Python berpotensi mengubah sistem, perlu konfirmasi.", True)
        if "rm -rf /" in lowered or "shutil.rmtree('/')" in lowered:
            return PermissionDecision(False, "Kode Python destruktif diblokir.")
        return PermissionDecision(True)

    def check_file(self, action: str, path: Path) -> PermissionDecision:
        if is_sensitive_file(path) and action == "read":
            return PermissionDecision(True, "File sensitif. Output akan direduksi dan perlu konfirmasi.", True)
        if action in {"write", "append", "delete"}:
            if self.safety_mode in {"safe", "balanced"}:
                return PermissionDecision(True, f"Aksi file {action} perlu konfirmasi.", True)
        return PermissionDecision(True)

    def confirm_if_needed(self, decision: PermissionDecision, prompt: str, console: Any | None = None) -> bool:
        if not decision.allowed:
            if console:
                console.print(f"[red]{decision.reason}[/red]")
            return False
        if not decision.requires_confirmation:
            return True
        if not self.interactive:
            if console:
                console.print(f"[yellow]Ditolak: {decision.reason}[/yellow]")
            return False
        if console and hasattr(console, "confirm"):
            return bool(console.confirm(f"{prompt}\n{decision.reason}\nLanjutkan?", default=False))
        return ask_confirm(f"{prompt}\n{decision.reason}\nLanjutkan?", default=False)


def ask_confirm(message: str, default: bool = False) -> bool:
    try:
        import questionary

        return bool(questionary.confirm(message, default=default).ask())
    except Exception:
        suffix = "y/N" if not default else "Y/n"
        answer = input(f"{message} [{suffix}] ").strip().lower()
        if not answer:
            return default
        return answer in {"y", "yes", "ya", "iya"}


def is_extreme_command(command: str) -> bool:
    return any(re.search(pattern, command, re.IGNORECASE | re.DOTALL) for pattern in EXTREME_BLOCK_PATTERNS)


def is_risky_command(command: str) -> bool:
    return any(re.search(pattern, command, re.IGNORECASE | re.DOTALL) for pattern in RISKY_PATTERNS)


def is_read_only_command(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    base = Path(parts[0]).name
    if base not in READ_ONLY_COMMANDS:
        return False
    write_markers = {">", ">>", "tee", "xargs", "-exec"}
    return not any(marker in command for marker in write_markers)


def is_sensitive_file(path: Path) -> bool:
    name = path.name.lower()
    full = str(path).lower()
    for pattern in SENSITIVE_PATTERNS:
        p = pattern.lower()
        if fnmatch.fnmatch(name, p) or p in full:
            return True
    return False


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_REGEXES:
        if "Bearer" in pattern.pattern:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        elif "API" in pattern.pattern:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    for key in [
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "TAVILY_API_KEY",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "TOGETHER_API_KEY",
        "DEEPINFRA_API_KEY",
        "FIREWORKS_API_KEY",
        "MISTRAL_API_KEY",
        "XAI_API_KEY",
        "PERPLEXITY_API_KEY",
        "DEEPSEEK_API_KEY",
        "CEREBRAS_API_KEY",
        "CUSTOM_PROVIDER_API_KEY",
    ]:
        value = os.environ.get(key)
        if value and len(value) > 4:
            redacted = redacted.replace(value, f"{value[:4]}...[REDACTED]")
    return redacted


def safe_path_display(path: Path) -> str:
    home = str(Path.home())
    text = str(path)
    if text.startswith(home):
        return "~" + text[len(home) :]
    return text
