from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from core.permissions import PermissionManager, redact_secrets

from .base import SkillResult, truncate


class BashExecSkill:
    name = "bash_exec"
    description = "Jalankan command shell lokal dengan timeout dan permission check."
    parameters_schema = {"command": "Command sh/bash/powershell.", "timeout": "Timeout detik, default 30."}

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
        command = str(args.get("command", "")).strip()
        timeout = int(args.get("timeout") or 30)
        timeout = max(1, min(timeout, 120))
        permission: PermissionManager = context["permission"]
        console = context.get("console")
        decision = permission.check_command(command)
        if not permission.confirm_if_needed(decision, f"Jalankan command?\n{command}", console):
            return SkillResult(False, "Command tidak dijalankan.")

        workspace = str(context["workspace"])
        shell = _shell_for(context.get("platform_info"))
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=workspace,
                executable=shell if os.name != "nt" else None,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or "") + (exc.stderr or "")
            return SkillResult(False, f"Command timeout setelah {timeout}s.\n{redact_secrets(out)}")
        except OSError as exc:
            return SkillResult(False, f"Gagal menjalankan command: {exc}")

        full = (completed.stdout or "") + (completed.stderr or "")
        full = redact_secrets(full)
        status = "OK" if completed.returncode == 0 else f"exit {completed.returncode}"
        shown, truncated = truncate(full, int(context.get("max_output_length", 6000)))
        output = f"$ {command}\n[{status}]\n{shown}".rstrip()
        return SkillResult(completed.returncode == 0, output, full if truncated else None, {"command": command})


def _shell_for(platform_info: Any) -> str | None:
    if os.name == "nt":
        return None
    for candidate in ["bash", "sh"]:
        path = shutil.which(candidate)
        if path:
            return path
    return "/bin/sh"
