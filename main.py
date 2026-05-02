from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import requests
from rich.table import Table

from core import __version__
from core.agent import Agent
from core.config import ConfigManager, DEFAULT_CONFIG, SECRET_ENV_KEYS
from core.llm import build_provider
from core.platform import PlatformInfo, detect_platform, ensure_app_dirs
from core.permissions import PermissionManager
from core.prompt_context import attachment_notice, build_file_context
from core.provider_catalog import (
    OPENAI_COMPATIBLE_PROVIDERS,
    OPENROUTER_CURATED_MODEL_IDS,
    OPENROUTER_FALLBACK_MODEL_CHOICES,
    OPENROUTER_FLAGSHIP_MODEL_IDS,
    PROVIDER_LABELS,
    get_provider_option,
    normalize_provider_name,
    provider_from_label,
)
from core.router import CommandRouter
from core.session import SessionManager
from providers.base import ProviderError
from skills import load_builtin_skills
from ui.activity import set_terminal_title, thinking_status
from ui.banner import print_banner, print_startup_box
from ui.chat_tui import ChatTUI
from ui.commands import skills_table
from ui.layout import clear_terminal, status_bar
from ui.panels import print_ai, print_error, print_info, print_tool
from ui.prompts import ask_confirm, ask_select, ask_text, prompt_input
from ui.theme import detect_ui_mode, make_console


PROJECT_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="NyalaCLI", description="Termux-first terminal AI agent.")
    parser.add_argument("command", nargs="?", default="help", choices=["setup", "chat", "config", "skills", "doctor", "reset", "version", "help"])
    args = parser.parse_args(argv)

    platform_info = detect_platform()
    config_manager = ConfigManager(platform_info)
    console = make_console()

    try:
        if args.command == "setup":
            return command_setup(config_manager, console)
        if args.command == "chat":
            return command_chat(config_manager, console)
        if args.command == "config":
            return command_config(config_manager, console)
        if args.command == "skills":
            return command_skills(console)
        if args.command == "doctor":
            return command_doctor(config_manager, console)
        if args.command == "reset":
            return command_reset(config_manager, console)
        if args.command == "version":
            console.print(f"NyalaCLI {__version__}")
            return 0
        parser.print_help()
        return 0
    except KeyboardInterrupt:
        console.print("\n[yellow]Dibatalkan.[/yellow]")
        return 130
    except Exception as exc:
        config = {}
        try:
            config = config_manager.load()
        except Exception:
            pass
        if config.get("debug"):
            raise
        console.print(f"[red]Error:[/red] {exc}")
        return 1


def command_setup(config_manager: ConfigManager, console) -> int:
    platform_info = config_manager.platform
    ensure_app_dirs(platform_info)
    ui_mode = detect_ui_mode()
    print_banner(console, ui_mode)

    console.print(_platform_table(platform_info))
    if platform_info.is_termux:
        console.print("[cyan]Termux detected[/cyan]")
        if not platform_info.storage_accessible:
            print_info(
                console,
                "Storage Termux belum terdeteksi.\n"
                "Jalankan `termux-setup-storage` jika ingin memakai ~/storage/shared.\n"
                "NyalaCLI tetap bisa lanjut dengan workspace internal.",
                ui_mode,
                "Termux Storage",
            )
            ask_confirm("Lanjut dengan workspace internal?", default=True)

    config = config_manager.load()
    provider_result = _configure_provider_until_valid(config, console, ui_mode)
    if provider_result is None:
        console.print("[yellow]Setup provider dibatalkan.[/yellow]")
        return 1
    provider_config, env_values = provider_result

    tavily = ask_text("Tavily API key untuk web_search (opsional)", password=True)
    if tavily:
        env_values[SECRET_ENV_KEYS["tavily"]] = tavily

    default_mode = "balanced" if platform_info.is_termux else "safe"
    safety_mode = ask_select("Safety mode", ["safe", "balanced", "freedom"], default_mode)
    workspace_default = str(platform_info.default_workspace)
    workspace = Path(ask_text("Workspace", workspace_default)).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)

    config.update(
        {
            **provider_config,
            "safety_mode": safety_mode,
            "workspace": str(workspace.resolve()),
        }
    )
    config_manager.save(config)
    config_manager.write_env(env_values)
    print_info(console, "Setup selesai. API key disimpan di ~/.nyalacli/.env dan tidak ditampilkan penuh.", ui_mode, "Setup")
    console.print("[cyan]Jalankan:[/cyan] python main.py chat")
    return 0


def _configure_provider_until_valid(
    current_config: dict[str, Any],
    console,
    ui_mode,
) -> tuple[dict[str, Any], dict[str, str]] | None:
    while True:
        provider_config, env_values = _ask_provider_settings(current_config)
        probe_config = dict(current_config)
        probe_config.update(provider_config)
        print_info(
            console,
            f"Menguji {probe_config['provider']} / {probe_config['model']} dengan prompt singkat...",
            ui_mode,
            "Provider Test",
        )
        ok, detail = validate_provider_config(probe_config, env_values)
        if ok:
            print_info(console, detail, ui_mode, "Provider Test")
            return provider_config, env_values
        print_error(console, detail, ui_mode)
        if not ask_confirm("Ganti provider/model/routing dan coba lagi?", default=True):
            return None


def _ask_provider_settings(current_config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    provider_label = ask_select("Pilih provider default", PROVIDER_LABELS, "OpenRouter")
    provider = provider_from_label(provider_label)
    option = get_provider_option(provider)
    base_url = current_config.get("base_url") or option.base_url or DEFAULT_CONFIG["base_url"]
    custom_provider_name = str(current_config.get("custom_provider_name") or option.label)

    if provider == "custom":
        custom_provider_name = ask_text("Nama custom provider", custom_provider_name or option.label).strip() or option.label

    if option.openai_compatible:
        base_default = option.base_url or str(base_url)
        if option.editable_base_url:
            base_url = ask_text("Base URL OpenAI-compatible", base_default).strip().rstrip("/")
        else:
            base_url = base_default

    model = _ask_model_id(provider, option.default_model)
    env_values: dict[str, str] = {}
    if option.api_key_env:
        value = ask_text(option.api_key_prompt, password=True)
        if value:
            env_values[option.api_key_env] = value

    routing = ""
    if provider == "openrouter":
        routing = ask_text(
            "Routing OpenRouter: auto, daftar slug, atau JSON object provider",
            current_config.get("routing") or "auto",
        )
        if routing.lower() == "auto":
            routing = ""

    return (
        {
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "routing": routing,
            "custom_provider_name": custom_provider_name,
        },
        env_values,
    )


def _ask_model_id(provider: str, default_model: str) -> str:
    if provider == "openrouter":
        choices = _openrouter_model_choices()
        custom_label = "Model ID custom..."
        selected = ask_select("Pilih model OpenRouter", list(choices) + [custom_label], next(iter(choices)))
        if selected != custom_label:
            return choices[selected]
        prompt = "Model ID OpenRouter custom"
    else:
        prompt = "Model ID"
    model = ""
    while not model:
        model = ask_text(prompt, default_model).strip()
    return model


def _openrouter_model_choices() -> dict[str, str]:
    choices: dict[str, str] = {}
    try:
        response = requests.get("https://openrouter.ai/api/v1/models", timeout=8)
        response.raise_for_status()
        data = response.json().get("data", [])
        if not isinstance(data, list):
            raise ValueError("format models tidak valid")
        models_by_id = {str(model.get("id")): model for model in data if isinstance(model, dict)}
        for model_id in OPENROUTER_CURATED_MODEL_IDS:
            if model_id == "openrouter/free":
                choices["OpenRouter Free Router"] = model_id
                continue
            if model_id == "openrouter/auto":
                choices["OpenRouter Auto Router"] = model_id
                continue
            model = models_by_id.get(model_id)
            if not model or not _model_is_text_or_multimodal_chat(model):
                continue
            if not _model_is_allowed_by_price(model):
                continue
            choices[_openrouter_choice_label(model, choices)] = str(model["id"])
    except (requests.RequestException, ValueError, KeyError):
        for label, model_id in OPENROUTER_FALLBACK_MODEL_CHOICES:
            choices.setdefault(label, model_id)
    return choices


def _model_is_text_or_multimodal_chat(model: dict[str, Any]) -> bool:
    architecture = model.get("architecture", {}) or {}
    output_modalities = architecture.get("output_modalities") or []
    input_modalities = architecture.get("input_modalities") or []
    if output_modalities != ["text"] or "text" not in input_modalities:
        return False
    searchable = f"{model.get('id', '')} {model.get('name', '')}".lower()
    excluded_terms = (
        "audio",
        "image-generation",
        "image-preview",
        "music",
        "speech",
        "tts",
        "video-generation",
        "embedding",
        "moderation",
        "guard",
        "lyra",
    )
    return not any(term in searchable for term in excluded_terms)


def _model_is_allowed_by_price(model: dict[str, Any]) -> bool:
    model_id = str(model.get("id", ""))
    if model_id in OPENROUTER_FLAGSHIP_MODEL_IDS:
        return True
    prompt_price, completion_price = _model_token_prices(model)
    blend_price_per_million = (prompt_price + completion_price) * 500_000
    return blend_price_per_million <= 5


def _model_token_prices(model: dict[str, Any]) -> tuple[float, float]:
    pricing = model.get("pricing", {}) or {}
    return _as_float(pricing.get("prompt")), _as_float(pricing.get("completion"))


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _openrouter_choice_label(model: dict[str, Any], existing: dict[str, str]) -> str:
    model_id = str(model.get("id", ""))
    name = str(model.get("name") or model_id).strip()
    if name not in existing:
        return name
    return f"{name} ({model_id})" if model_id else name


def validate_provider_config(config: dict[str, Any], env_values: dict[str, str] | None = None) -> tuple[bool, str]:
    probe_config = dict(config)
    probe_config["temperature"] = 0
    probe_config["max_tokens"] = max(8, min(int(probe_config.get("max_tokens", 64) or 64), 64))
    messages = [
        {"role": "system", "content": "You are checking whether an API endpoint is active."},
        {"role": "user", "content": "Reply with a short confirmation that the model is active."},
    ]
    try:
        with temporary_env(env_values or {}):
            provider = build_provider(probe_config)
            response = provider.chat(messages)
    except (ProviderError, ValueError, OSError) as exc:
        return False, f"Provider test gagal: {exc}"
    content = response.content.strip()
    if not content:
        return False, "Provider test gagal: model membalas kosong."
    preview = content.replace("\n", " ")[:160]
    return True, f"Provider aktif. Balasan test: {preview}"


@contextmanager
def temporary_env(values: dict[str, str]):
    old_values = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            os.environ[key] = value
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def command_chat(config_manager: ConfigManager, console) -> int:
    platform_info = config_manager.platform
    config = config_manager.load()
    Path(config.get("workspace", platform_info.default_workspace)).expanduser().mkdir(parents=True, exist_ok=True)
    ui_mode = detect_ui_mode(config)

    session_manager = SessionManager(platform_info)
    session = session_manager.create()
    skills = load_builtin_skills()
    history_path = platform_info.cache_dir / "prompt_history.txt"

    if _can_run_chat_tui(console):
        tui = ChatTUI(
            config_manager=config_manager,
            platform_info=platform_info,
            config=config,
            session=session,
            session_manager=session_manager,
            skills=skills,
            project_root=PROJECT_ROOT,
            ui_mode=ui_mode,
            provider_validator=validate_provider_config,
        )
        tui.doctor_callback = lambda: command_doctor(config_manager, tui.transcript_console)
        return tui.run()

    clear_terminal(console)
    set_terminal_title(console, "Nyala ready")
    print_startup_box(console, config, platform_info, ui_mode, __version__)

    def run_doctor_inline() -> None:
        command_doctor(config_manager, console)

    def run_provider_test_inline(active_config: dict[str, Any]) -> tuple[bool, str]:
        return validate_provider_config(active_config)

    while True:
        input_status = status_bar(config, session, ui_mode, platform_info).plain
        try:
            text = prompt_input(config, ui_mode, history_path, input_status)
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Keluar.[/yellow]")
            session_manager.save(session)
            return 0
        if not text:
            continue
        if text == "?":
            text = "/palette"
        if text.startswith("!"):
            command = text[1:].strip()
            if not command:
                print_error(console, "Pakai: !<command>", ui_mode)
                continue
            _run_shell_shortcut(command, config, session, skills, platform_info, console, ui_mode)
            session_manager.save(session)
            continue
        if text.startswith("/"):
            router = CommandRouter(
                {
                    "console": console,
                    "ui_mode": ui_mode,
                    "config": config,
                    "config_manager": config_manager,
                    "session": session,
                    "session_manager": session_manager,
                    "skills": skills,
                    "platform_info": platform_info,
                    "project_root": PROJECT_ROOT,
                    "doctor": run_doctor_inline,
                    "provider_validator": run_provider_test_inline,
                }
            )
            outcome = router.handle(text)
            if outcome.session_replaced is not None:
                session = outcome.session_replaced
            if outcome.clear:
                console.clear()
            if outcome.reload_provider:
                config = config_manager.load()
                ui_mode = detect_ui_mode(config)
            if outcome.exit_chat:
                session_manager.save(session)
                return 0
            session_manager.save(session)
            continue

        prompt_context, attachments = build_file_context(text, config.get("workspace", platform_info.default_workspace))
        notice = attachment_notice(attachments)
        if notice:
            print_info(console, notice, ui_mode, "Prompt Context")

        agent = Agent(config, session, skills, platform_info, console, ui_mode, PROJECT_ROOT, interactive_permissions=True)
        attached_count = len([item for item in attachments if item.included])
        with thinking_status(console, config, ui_mode, attached_files=attached_count):
            answer = agent.handle(text, prompt_context)
        print_ai(console, answer, ui_mode)
        session_manager.save(session)


def _can_run_chat_tui(console) -> bool:
    if not getattr(console, "is_terminal", False):
        return False
    try:
        import prompt_toolkit  # noqa: F401
    except Exception:
        return False
    return True


def command_config(config_manager: ConfigManager, console) -> int:
    config = config_manager.load()
    ui_mode = detect_ui_mode(config)
    print_info(console, json.dumps(config_manager.redacted_summary(), indent=2, ensure_ascii=False), ui_mode, "Config")
    return 0


def _run_shell_shortcut(command: str, config: dict[str, Any], session, skills: dict, platform_info, console, ui_mode) -> None:
    skill = skills.get("bash_exec")
    if not skill:
        print_error(console, "Skill bash_exec tidak tersedia.", ui_mode)
        return
    context = {
        "workspace": config.get("workspace", str(platform_info.default_workspace)),
        "config": config,
        "safety_mode": config.get("safety_mode", "balanced"),
        "console": console,
        "platform_info": platform_info,
        "permission": PermissionManager(config.get("safety_mode", "balanced"), interactive=True),
        "project_root": PROJECT_ROOT,
        "max_output_length": 3000 if ui_mode.compact else 6000,
    }
    session.add("user", f"!{command}", {"shell_shortcut": True})
    print_tool(console, "bash_exec", {"command": command}, "running", ui_mode)
    result = skill.run({"command": command}, context)
    print_tool(console, "bash_exec", {"command": command}, "done" if result.ok else "error", ui_mode, result.output)
    session.add("tool", result.output, {"tool": "bash_exec", "ok": result.ok, "shell_shortcut": True})


def command_skills(console) -> int:
    skills = load_builtin_skills()
    console.print(skills_table(skills))
    return 0


def command_doctor(config_manager: ConfigManager, console) -> int:
    platform_info = config_manager.platform
    config = config_manager.load()
    ui_mode = detect_ui_mode(config)
    table = Table(title="NyalaCLI Doctor", expand=True)
    table.add_column("Check", style="nyala.cyan")
    table.add_column("Status")
    table.add_column("Detail", style="nyala.dim")

    add_check(table, "Platform", True, platform_info.label)
    add_check(table, "Termux detected", platform_info.is_termux, "yes" if platform_info.is_termux else "no")
    add_check(table, "Python version", sys.version_info >= (3, 10), sys.version.split()[0])
    add_check(table, "pip", bool(shutil.which("pip") or importlib.util.find_spec("pip")), shutil.which("pip") or "python -m pip")
    add_check(table, "git", bool(shutil.which("git")), shutil.which("git") or "missing")
    add_check(table, "curl", bool(shutil.which("curl")), shutil.which("curl") or "missing")
    add_check(table, "Termux storage", platform_info.storage_accessible, str(platform_info.storage_shared))
    add_check(table, "Config dir writable", is_writable(platform_info.config_dir), str(platform_info.config_dir))
    workspace = Path(config.get("workspace", platform_info.default_workspace)).expanduser()
    add_check(table, "Workspace writable", is_writable(workspace), str(workspace))
    for package, import_name in {
        "rich": "rich",
        "prompt_toolkit": "prompt_toolkit",
        "questionary": "questionary",
        "requests": "requests",
        "python-dotenv": "dotenv",
        "beautifulsoup4": "bs4",
    }.items():
        add_check(table, f"Dependency {package}", importlib.util.find_spec(import_name) is not None, import_name)
    secret_status = config_manager.secret_status()
    active_provider = normalize_provider_name(str(config.get("provider", "openrouter")))
    active_option = get_provider_option(active_provider)
    active_secret_key = active_option.api_key_env
    if active_secret_key:
        active_secret_ok = bool(os.environ.get(active_secret_key))
        secret_detail = "configured" if active_secret_ok else f"missing {active_secret_key}"
        add_check(table, f"{active_option.label} key", active_secret_ok or active_option.api_key_optional, secret_detail)
    add_check(table, "Tavily key", secret_status["tavily"], "configured" if secret_status["tavily"] else "missing")
    if active_provider in OPENAI_COMPATIBLE_PROVIDERS and active_option.editable_base_url:
        ok, detail = check_local_endpoint(str(config.get("base_url", "")))
        add_check(table, "OpenAI-compatible endpoint", ok, detail)
    else:
        table.add_row("OpenAI-compatible endpoint", "[dim]SKIP[/dim]", "provider aktif bukan local/custom")
    ok, detail = validate_provider_config(config)
    add_check(table, "Active provider prompt test", ok, detail)

    console.print(table)
    if platform_info.is_termux and not platform_info.storage_accessible:
        print_info(console, "Untuk storage Android, jalankan: termux-setup-storage", ui_mode, "Termux Tip")
    return 0


def command_reset(config_manager: ConfigManager, console) -> int:
    ui_mode = detect_ui_mode()
    if not ask_confirm("Reset config NyalaCLI? File .env dan sessions tidak dihapus.", default=False):
        console.print("[yellow]Reset dibatalkan.[/yellow]")
        return 0
    platform_info = config_manager.platform
    config = dict(DEFAULT_CONFIG)
    config["safety_mode"] = "balanced" if platform_info.is_termux else "safe"
    config["workspace"] = str(platform_info.default_workspace)
    config_manager.save(config)
    print_info(console, "Config direset. Secrets dan sessions tetap ada.", ui_mode, "Reset")
    return 0


def _platform_table(platform_info: PlatformInfo) -> Table:
    table = Table(title="Platform", expand=True)
    table.add_column("Item", style="nyala.cyan")
    table.add_column("Value")
    table.add_row("OS", platform_info.label)
    table.add_row("Home", str(platform_info.home))
    table.add_row("Config", str(platform_info.config_dir))
    table.add_row("Default workspace", str(platform_info.default_workspace))
    table.add_row("Storage access", "yes" if platform_info.storage_accessible else "no")
    return table


def add_check(table: Table, name: str, ok: bool, detail: str) -> None:
    status = "[green]OK[/green]" if ok else "[red]MISS[/red]"
    table.add_row(name, status, detail)


def is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".nyalacli_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def check_local_endpoint(base_url: str) -> tuple[bool, str]:
    if not base_url:
        return False, "base_url empty"
    try:
        response = requests.get(base_url.rstrip("/") + "/models", timeout=2)
    except requests.RequestException as exc:
        return False, str(exc)[:120]
    return response.status_code < 500, f"HTTP {response.status_code}"


if __name__ == "__main__":
    raise SystemExit(main())
