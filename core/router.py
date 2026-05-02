from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.table import Table

from skills.file_manager import FileManagerSkill
from ui.commands import help_table, palette_table, skills_table
from ui.home import print_home_screen
from ui.panels import print_ai, print_error, print_info
from ui.prompts import ask_select, ask_text

from .memory import compact_history
from .provider_catalog import PROVIDER_OPTIONS, get_provider_option, normalize_provider_name
from .reasoning import EFFORT_LABELS, effort_display, model_supports_thinking, normalize_effort
from .team import NyalaTeam
from .token_counter import token_report


@dataclass
class CommandOutcome:
    handled: bool = True
    exit_chat: bool = False
    reload_provider: bool = False
    clear: bool = False
    session_replaced: Any = None


class CommandRouter:
    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context

    def handle(self, line: str) -> CommandOutcome:
        parts = line.strip().split(maxsplit=1)
        command = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        console = self.context["console"]
        ui_mode = self.context["ui_mode"]
        config = self.context["config"]
        config_manager = self.context["config_manager"]
        session = self.context["session"]
        session_manager = self.context["session_manager"]
        skills = self.context["skills"]

        if command in {"/exit", "/quit"}:
            return CommandOutcome(exit_chat=True)
        if command == "/help":
            console.print(help_table())
            return CommandOutcome()
        if command == "/home":
            console.clear()
            print_home_screen(console, config, session, session_manager, self.context["platform_info"], skills, ui_mode)
            return CommandOutcome()
        if command in {"/palette", "/commands"}:
            console.print(palette_table())
            return CommandOutcome()
        if command == "/config":
            print_info(console, _format_config(config_manager.redacted_summary()), ui_mode, "Config")
            return CommandOutcome()
        if command == "/stream":
            value = arg.strip().lower()
            if value in {"", "status"}:
                state = "on" if config.get("stream", False) else "off"
                print_info(console, f"Streaming output: {state}\nPakai: /stream true atau /stream false", ui_mode, "Stream")
                return CommandOutcome()
            if value not in {"true", "false", "on", "off", "1", "0", "yes", "no"}:
                print_error(console, "Pakai: /stream true atau /stream false", ui_mode)
                return CommandOutcome()
            enabled = value in {"true", "on", "1", "yes"}
            config["stream"] = enabled
            config_manager.save(config)
            print_info(console, f"Streaming output: {'on' if enabled else 'off'}", ui_mode, "Stream")
            return CommandOutcome()
        if command == "/skills":
            console.print(skills_table(skills))
            return CommandOutcome()
        if command == "/model":
            if not arg:
                print_error(console, "Pakai: /model <model_id>", ui_mode)
                return CommandOutcome()
            previous = dict(config)
            config["model"] = arg.strip()
            if not self._save_provider_change(previous):
                return CommandOutcome(reload_provider=True)
            print_info(console, f"Model aktif: {config['model']}", ui_mode)
            return CommandOutcome(reload_provider=True)
        if command == "/provider":
            provider = normalize_provider_name(arg.strip())
            if provider not in PROVIDER_OPTIONS:
                valid = ", ".join(PROVIDER_OPTIONS)
                print_error(console, f"Provider valid: {valid}", ui_mode)
                return CommandOutcome()
            previous = dict(config)
            option = get_provider_option(provider)
            config["provider"] = provider
            config["model"] = option.default_model
            if option.openai_compatible and option.editable_base_url:
                config["base_url"] = option.base_url
            elif provider == "openrouter":
                config["routing"] = config.get("routing", "")
            if not self._save_provider_change(previous):
                return CommandOutcome(reload_provider=True)
            print_info(console, f"Provider aktif: {config['provider']} | model default: {config['model']}", ui_mode)
            return CommandOutcome(reload_provider=True)
        if command == "/routing":
            previous = dict(config)
            config["routing"] = arg.strip()
            if not self._save_provider_change(previous):
                return CommandOutcome(reload_provider=True)
            print_info(console, f"Routing OpenRouter: {config['routing'] or 'auto'}", ui_mode)
            return CommandOutcome(reload_provider=True)
        if command == "/effort":
            if not arg.strip():
                valid = ", ".join(EFFORT_LABELS.values())
                print_info(console, f"Thinking effort: {effort_display(config.get('thinking_effort'))}\nValid: {valid}, off", ui_mode)
                return CommandOutcome()
            try:
                effort = normalize_effort(arg)
            except ValueError as exc:
                print_error(console, str(exc), ui_mode)
                return CommandOutcome()
            if not effort:
                config["thinking_effort"] = ""
                config_manager.save(config)
                print_info(console, "Thinking effort: off", ui_mode)
                return CommandOutcome(reload_provider=True)
            ok, reason = model_supports_thinking(config)
            if not ok:
                print_error(console, f"/effort diblokir.\n{reason}", ui_mode)
                return CommandOutcome()
            config["thinking_effort"] = effort
            config_manager.save(config)
            print_info(console, f"Thinking effort: {effort_display(effort)}\n{reason}", ui_mode)
            return CommandOutcome(reload_provider=True)
        if command in {"/base-url", "/endpoint"}:
            base_url = arg.strip().rstrip("/")
            if not base_url:
                print_error(console, f"Pakai: {command} <base_url>", ui_mode)
                return CommandOutcome()
            previous = dict(config)
            config["base_url"] = base_url
            if not self._save_provider_change(previous):
                return CommandOutcome(reload_provider=True)
            print_info(console, f"Base URL aktif: {config['base_url']}", ui_mode)
            return CommandOutcome(reload_provider=True)
        if command in {"/provider-test", "/test-provider"}:
            validator = self.context.get("provider_validator")
            if not validator:
                print_error(console, "Provider validator tidak tersedia.", ui_mode)
                return CommandOutcome()
            ok, detail = validator(config)
            if ok:
                print_info(console, detail, ui_mode, "Provider Test")
            else:
                print_error(console, detail, ui_mode)
            return CommandOutcome()
        if command in {"/token", "/context", "/usage", "/stats"}:
            report = token_report(session.messages, session.last_response_tokens)
            print_info(console, _format_config(report), ui_mode, "Context")
            return CommandOutcome()
        if command == "/save":
            sid = arg.strip() or session.session_id
            path = session_manager.save(session, sid)
            print_info(console, f"Session disimpan: {path}", ui_mode)
            return CommandOutcome()
        if command == "/load":
            sid = arg.strip()
            if not sid:
                print_error(console, "Pakai: /load <session_id>", ui_mode)
                return CommandOutcome()
            try:
                new_session = session_manager.load(sid)
            except Exception as exc:
                print_error(console, f"Gagal load session: {exc}", ui_mode)
                return CommandOutcome()
            print_info(console, f"Session loaded: {sid}", ui_mode)
            return CommandOutcome(session_replaced=new_session)
        if command in {"/resume", "/continue"}:
            sid = arg.strip()
            if not sid:
                sessions = session_manager.list_sessions()
                sid = str(sessions[0]["id"]) if sessions else ""
            if not sid:
                print_error(console, "Belum ada session tersimpan.", ui_mode)
                return CommandOutcome()
            try:
                new_session = session_manager.load(sid)
            except Exception as exc:
                print_error(console, f"Gagal resume session: {exc}", ui_mode)
                return CommandOutcome()
            print_info(console, f"Resumed session: {sid}", ui_mode)
            return CommandOutcome(session_replaced=new_session)
        if command == "/sessions":
            console.print(_sessions_table(session_manager.list_sessions()))
            return CommandOutcome()
        if command == "/compact":
            memory, recent = compact_history(session.messages)
            session.memory = memory
            session.messages = recent
            session_manager.save(session)
            print_info(console, "History lama diringkas ke memory lokal.", ui_mode)
            return CommandOutcome()
        if command == "/clear":
            return CommandOutcome(clear=True)
        if command == "/safe":
            value = arg.strip().lower()
            config["safety_mode"] = "safe" if value == "on" else "freedom" if value == "off" else config.get("safety_mode", "balanced")
            config_manager.save(config)
            print_info(console, f"Safety mode: {config['safety_mode']}", ui_mode)
            return CommandOutcome(reload_provider=True)
        if command == "/mode":
            value = arg.strip().lower()
            if value not in {"safe", "balanced", "freedom"}:
                print_error(console, "Mode valid: safe, balanced, freedom", ui_mode)
                return CommandOutcome()
            config["safety_mode"] = value
            config_manager.save(config)
            print_info(console, f"Safety mode: {value}", ui_mode)
            return CommandOutcome(reload_provider=True)
        if command == "/workspace":
            path = Path(arg.strip()).expanduser() if arg.strip() else None
            if not path:
                print_error(console, "Pakai: /workspace <path>", ui_mode)
                return CommandOutcome()
            path.mkdir(parents=True, exist_ok=True)
            config["workspace"] = str(path.resolve())
            config_manager.save(config)
            print_info(console, f"Workspace: {config['workspace']}", ui_mode)
            return CommandOutcome(reload_provider=True)
        if command == "/pwd":
            print_info(console, str(config.get("workspace")), ui_mode, "Workspace")
            return CommandOutcome()
        if command == "/tree":
            skill = FileManagerSkill()
            result = skill.tree(Path(config.get("workspace", ".")), 3)
            print_info(console, result.output, ui_mode, "Tree")
            return CommandOutcome()
        if command == "/configure" and arg.strip().lower() == "team":
            self._configure_team()
            return CommandOutcome(reload_provider=True)
        if command == "/team":
            if not arg.strip():
                print_error(console, "Pakai: /team <task>", ui_mode)
                return CommandOutcome()
            team = NyalaTeam(
                config,
                session,
                skills,
                self.context["platform_info"],
                console,
                ui_mode,
                self.context["project_root"],
            )
            final = team.run(arg.strip())
            session.add("assistant", final, {"team": True})
            return CommandOutcome()
        if command == "/doctor":
            doctor = self.context.get("doctor")
            if doctor:
                doctor()
            return CommandOutcome()

        print_error(console, f"Command tidak dikenal: {command}. Ketik /help.", ui_mode)
        return CommandOutcome()

    def _save_provider_change(self, previous: dict[str, Any]) -> bool:
        config = self.context["config"]
        config_manager = self.context["config_manager"]
        console = self.context["console"]
        ui_mode = self.context["ui_mode"]
        validator = self.context.get("provider_validator")
        if config.get("thinking_effort"):
            ok, reason = model_supports_thinking(config)
            if not ok:
                config["thinking_effort"] = ""
                print_info(console, f"Thinking effort dimatikan otomatis.\n{reason}", ui_mode)
            elif "Gagal cek metadata" in reason:
                print_info(console, f"Thinking effort tetap aktif.\n{reason}", ui_mode)
        if validator:
            ok, detail = validator(config)
            if not ok:
                config.clear()
                config.update(previous)
                config_manager.save(config)
                print_error(console, f"{detail}\nPilihan tidak disimpan. Ganti provider/model/routing lalu coba lagi.", ui_mode)
                return False
            print_info(console, detail, ui_mode, "Provider Test")
        config_manager.save(config)
        return True

    def _configure_team(self) -> None:
        config = self.context["config"]
        config_manager = self.context["config_manager"]
        team = dict(config.get("team", {}))
        planners = ask_select("Jumlah Planner", ["0", "1", "2"], str(team.get("planners", 1)))
        runners = ask_select("Jumlah Runner", [str(i) for i in range(1, 8)], str(team.get("runners", 2)))
        roles = ask_text("Role runner, pisahkan koma", ",".join(team.get("roles", ["coder", "researcher"])))
        team["planners"] = int(planners)
        team["runners"] = int(runners)
        team["roles"] = [role.strip() for role in roles.split(",") if role.strip()] or ["general"]
        config["team"] = team
        config_manager.save(config)
        print_info(self.context["console"], "Konfigurasi NyalaTeam tersimpan.", self.context["ui_mode"])


def _format_config(data: dict[str, Any]) -> str:
    lines = []
    for key, value in data.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _sessions_table(rows: list[dict[str, Any]]) -> Table:
    table = Table(title="Sessions", expand=True)
    table.add_column("ID", style="nyala.cyan")
    table.add_column("Messages", justify="right")
    table.add_column("Updated", style="nyala.dim")
    for row in rows:
        table.add_row(str(row["id"]), str(row["messages"]), str(row["updated_at"]))
    return table
