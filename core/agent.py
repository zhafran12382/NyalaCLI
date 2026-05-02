from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from providers.base import ProviderError
from skills.base import SkillResult
from ui.panels import print_tool
from ui.theme import UiMode

from .llm import build_provider
from .memory import memory_to_prompt
from .permissions import PermissionManager, redact_secrets
from .token_counter import estimate_tokens


SYSTEM_PROMPT = """Kamu adalah NyalaCLI, AI agent terminal-first untuk Termux Android.

Gaya:
- Jawab ringkas tapi berguna.
- Utamakan layar HP portrait: padat, jelas, tidak bertele-tele.
- Gunakan bahasa user.

Aturan tool:
- Gunakan tools hanya jika perlu.
- Output tool call harus JSON valid tanpa teks tambahan:
  {"tool":"nama_tool","args":{"key":"value"}}
- Jangan menjalankan command destructive.
- Hormati workspace. Jangan keluar dari workspace kecuali user jelas meminta.
- Operasi berisiko harus minta izin atau akan melewati permission system.
- Jika sudah cukup, beri final answer biasa, bukan JSON.
"""


class _StreamGate:
    def __init__(self, on_delta: Callable[[str], None]) -> None:
        self._on_delta = on_delta
        self._buffer = ""
        self._started = False
        self._suppressed_json = False
        self._disabled = False

    def __call__(self, delta: str) -> None:
        if self._disabled or self._suppressed_json or not delta:
            return
        if not self._started:
            self._buffer += delta
            stripped = self._buffer.lstrip()
            if not stripped:
                return
            if stripped.startswith("{"):
                self._suppressed_json = True
                return
            self._started = True
            self._on_delta(self._buffer)
            self._buffer = ""
            return
        self._on_delta(delta)

    def finish(self, final: str) -> bool:
        if self._disabled or self._suppressed_json:
            return False
        if self._buffer:
            self._started = True
            self._on_delta(self._buffer)
            self._buffer = ""
        return self._started

    def disable(self) -> None:
        self._disabled = True
        self._buffer = ""


class Agent:
    def __init__(
        self,
        config: dict[str, Any],
        session,
        skills: dict[str, Any],
        platform_info,
        console,
        ui_mode: UiMode,
        project_root: Path,
        interactive_permissions: bool = True,
    ) -> None:
        self.config = config
        self.session = session
        self.skills = skills
        self.platform_info = platform_info
        self.console = console
        self.ui_mode = ui_mode
        self.project_root = project_root
        provider_config = dict(config)
        provider_config["_request_log_path"] = str(platform_info.logs_dir / "model_requests.log")
        provider_config["_session_id"] = session.session_id
        self.provider = build_provider(provider_config)
        self.permission = PermissionManager(config.get("safety_mode", "balanced"), interactive=interactive_permissions)
        self.max_steps = int(config.get("max_tool_steps", 8))
        self._turn_context = ""

    def handle(self, user_text: str, prompt_context: str = "", on_delta: Callable[[str], None] | None = None) -> str:
        self.session.add("user", user_text)
        self._turn_context = prompt_context
        final = ""
        try:
            for step in range(1, self.max_steps + 1):
                messages = self._messages_for_model()
                stream_gate = _StreamGate(on_delta) if on_delta and self.config.get("stream", False) else None
                try:
                    response = self._chat(messages, stream_gate)
                except ProviderError as exc:
                    self._log_provider_error(exc)
                    final = self._format_provider_error(exc)
                    self.session.add("assistant", final)
                    self.session.last_response_tokens = estimate_tokens(final)
                    return final
                except Exception as exc:
                    final = f"LLM error: {exc}"
                    self.session.add("assistant", final)
                    self.session.last_response_tokens = estimate_tokens(final)
                    return final

                content = response.content.strip()
                self.session.last_response_tokens = response.completion_tokens or estimate_tokens(content)
                tool_call, parse_error = self._parse_tool_call(content)
                if parse_error:
                    repaired = self._repair_tool_json(content)
                    if repaired:
                        tool_call = repaired
                        parse_error = ""
                if tool_call:
                    tool_name = str(tool_call.get("tool", "")).strip()
                    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
                    self.session.add("assistant", json.dumps(tool_call, ensure_ascii=False), {"tool_call": True})
                    result = self._run_tool(tool_name, args)
                    self.session.add(
                        "tool",
                        result.output,
                        {"tool": tool_name, "ok": result.ok, **(result.metadata or {})},
                    )
                    continue
                if parse_error:
                    self.session.add("assistant", content)
                    final = content + "\n\nCatatan: tool call JSON tidak valid, jadi saya perlakukan sebagai jawaban biasa."
                    if stream_gate:
                        stream_gate.finish(final)
                    return final
                final = content
                if stream_gate:
                    stream_gate.finish(final)
                self.session.add("assistant", final)
                return final

            final = f"Batas tool loop tercapai ({self.max_steps} langkah). Jalankan ulang dengan instruksi lebih spesifik."
            self.session.add("assistant", final)
            self.session.last_response_tokens = estimate_tokens(final)
            return final
        finally:
            self._turn_context = ""

    def _chat(self, messages: list[dict[str, str]], stream_gate: "_StreamGate | None") -> Any:
        if stream_gate and hasattr(self.provider, "chat_stream"):
            try:
                return self.provider.chat_stream(messages, stream_gate)
            except ProviderError as exc:
                if exc.status_code in {400, 404, 422}:
                    stream_gate.disable()
                    return self.provider.chat(messages)
                raise
        return self.provider.chat(messages)

    def _messages_for_model(self) -> list[dict[str, str]]:
        workspace = self.config.get("workspace", str(self.platform_info.default_workspace))
        system = "\n".join(
            [
                SYSTEM_PROMPT,
                f"Safety mode: {self.config.get('safety_mode', 'balanced')}",
                f"Workspace: {workspace}",
                f"Platform: {self.platform_info.label}",
                memory_to_prompt(self.session.memory),
                "Tools tersedia:",
                self._tool_docs(),
            ]
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for message in self.session.messages[-30:]:
            role = str(message.get("role", "user"))
            content = str(message.get("content", ""))
            if role == "tool":
                messages.append({"role": "user", "content": f"TOOL RESULT:\n{content}"})
            elif role in {"user", "assistant"}:
                messages.append({"role": role, "content": content})
        if self._turn_context:
            messages.append({"role": "user", "content": "ATTACHED FILE CONTEXT:\n" + self._turn_context})
        return messages

    def _tool_docs(self) -> str:
        lines = []
        for name, skill in sorted(self.skills.items()):
            schema = getattr(skill, "parameters_schema", {})
            lines.append(f"- {name}: {getattr(skill, 'description', '')}. Args: {json.dumps(schema, ensure_ascii=False)}")
        return "\n".join(lines)

    def _run_tool(self, tool_name: str, args: dict[str, Any]) -> SkillResult:
        skill = self.skills.get(tool_name)
        if not skill:
            return SkillResult(False, f"Tool tidak dikenal: {tool_name}")
        context = {
            "workspace": self.config.get("workspace", str(self.platform_info.default_workspace)),
            "config": self.config,
            "safety_mode": self.config.get("safety_mode", "balanced"),
            "console": self.console,
            "platform_info": self.platform_info,
            "permission": self.permission,
            "project_root": self.project_root,
            "max_output_length": 6000 if not self.ui_mode.compact else 3000,
        }
        print_tool(self.console, tool_name, args, "running", self.ui_mode)
        started = time.monotonic()
        try:
            result = skill.run(args, context)
        except Exception as exc:
            result = SkillResult(False, f"Tool error: {exc}")
        duration = time.monotonic() - started
        print_tool(self.console, tool_name, args, "done" if result.ok else "error", self.ui_mode, result.output)
        self._log_tool_call(tool_name, args, result, duration)
        return result

    def _log_tool_call(self, tool_name: str, args: dict[str, Any], result: SkillResult, duration: float) -> None:
        log_path = self.platform_info.logs_dir / "tool_calls.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session.session_id,
            "tool": tool_name,
            "args": redact_secrets(json.dumps(args, ensure_ascii=False)),
            "status": "ok" if result.ok else "error",
            "duration": round(duration, 3),
            "output_preview": redact_secrets((result.output or "")[:800]),
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _format_provider_error(self, exc: ProviderError) -> str:
        return exc.summary() + f"\nlog: {self.platform_info.logs_dir / 'provider_errors.log'}"

    def _log_provider_error(self, exc: ProviderError) -> None:
        log_path = self.platform_info.logs_dir / "provider_errors.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session.session_id,
            "provider": self.config.get("provider"),
            "model": self.config.get("model"),
            **exc.full_report(),
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(redact_secrets(json.dumps(row, ensure_ascii=False)) + "\n")

    def _parse_tool_call(self, content: str) -> tuple[dict[str, Any] | None, str]:
        candidate = extract_json_candidate(content)
        if not candidate:
            return None, ""
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            if '"tool"' in candidate or "'tool'" in candidate:
                return None, str(exc)
            return None, ""
        if isinstance(data, dict) and "tool" in data:
            return data, ""
        return None, ""

    def _repair_tool_json(self, content: str) -> dict[str, Any] | None:
        candidate = extract_json_candidate(content) or content
        repaired = candidate.strip()
        repaired = repaired.replace("'", '"')
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError:
            try:
                repair_prompt = (
                    "Perbaiki tool call berikut menjadi JSON valid saja tanpa teks lain. "
                    "Format wajib: {\"tool\":\"nama_tool\",\"args\":{...}}\n\n"
                    f"{content}"
                )
                response = self.provider.chat(self._messages_for_model() + [{"role": "user", "content": repair_prompt}])
                data = json.loads(extract_json_candidate(response.content) or response.content)
            except Exception:
                return None
        return data if isinstance(data, dict) and "tool" in data else None


def extract_json_candidate(text: str) -> str | None:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    match = re.search(r"(\{\s*[\"']tool[\"']\s*:.*\})", stripped, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return None
