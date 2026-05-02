from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from core.permissions import PermissionManager, redact_secrets

from .base import SkillResult, truncate


class PythonExecSkill:
    name = "python_exec"
    description = "Jalankan script Python sementara dengan timeout."
    parameters_schema = {"code": "Kode Python.", "timeout": "Timeout detik, default 20."}

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
        code = str(args.get("code", ""))
        timeout = int(args.get("timeout") or 20)
        timeout = max(1, min(timeout, 90))
        permission: PermissionManager = context["permission"]
        console = context.get("console")
        decision = permission.check_python_code(code)
        if not permission.confirm_if_needed(decision, "Jalankan kode Python sementara?", console):
            return SkillResult(False, "Kode Python tidak dijalankan.")

        cache_dir = Path(context["platform_info"].cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        script_path = cache_dir / f"nyala_exec_{uuid.uuid4().hex}.py"
        script_path.write_text(code, encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(context["workspace"]),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or "") + (exc.stderr or "")
            return SkillResult(False, f"Python timeout setelah {timeout}s.\n{redact_secrets(out)}")
        except OSError as exc:
            return SkillResult(False, f"Gagal menjalankan Python: {exc}")
        finally:
            try:
                script_path.unlink()
            except OSError:
                pass

        full = redact_secrets((completed.stdout or "") + (completed.stderr or ""))
        status = "OK" if completed.returncode == 0 else f"exit {completed.returncode}"
        shown, truncated = truncate(full, int(context.get("max_output_length", 6000)))
        return SkillResult(completed.returncode == 0, f"[{status}]\n{shown}".strip(), full if truncated else None)
