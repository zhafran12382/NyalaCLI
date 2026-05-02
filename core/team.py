from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.progress import Progress, SpinnerColumn, TextColumn

from providers.base import ProviderError
from ui.panels import print_ai, print_error, print_info

from .agent import Agent
from .llm import build_provider


class NyalaTeam:
    def __init__(self, config: dict[str, Any], session, skills, platform_info, console, ui_mode, project_root: Path) -> None:
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

    def run(self, task: str) -> str:
        team_config = self.config.get("team", {}) if isinstance(self.config.get("team"), dict) else {}
        planner_count = max(0, min(int(team_config.get("planners", 1)), 2))
        runner_count = max(1, min(int(team_config.get("runners", 2)), 7))
        roles = team_config.get("roles") or ["general"]
        print_info(self.console, f"Task: {task}\nPlanner: {planner_count}\nRunner: {runner_count}", self.ui_mode, "NyalaTeam")

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=self.console) as progress:
            lead_task = progress.add_task("Lead planning", total=None)
            plan = self._lead_plan(task, runner_count, roles)
            progress.update(lead_task, completed=1, visible=False)

            if planner_count:
                planner_task = progress.add_task("Planner splitting", total=None)
                plan = self._planner_refine(task, plan, planner_count)
                progress.update(planner_task, completed=1, visible=False)

            results: list[str] = []
            for idx, item in enumerate(plan[:runner_count], start=1):
                role = item.get("role") or roles[(idx - 1) % len(roles)]
                subtask = item.get("task") or task
                run_task = progress.add_task(f"Runner {idx} ({role}) working", total=None)
                result = self._runner(role, subtask)
                results.append(f"Runner {idx} ({role})\nTask: {subtask}\nResult:\n{result}")
                progress.update(run_task, completed=1, visible=False)

            synth_task = progress.add_task("Lead final synthesis", total=None)
            final = self._synthesize(task, results)
            progress.update(synth_task, completed=1, visible=False)

        print_ai(self.console, final, self.ui_mode)
        return final

    def _lead_plan(self, task: str, runner_count: int, roles: list[str]) -> list[dict[str, str]]:
        prompt = (
            "Kamu Lead NyalaTeam. Buat rencana JSON array untuk runner. "
            "Setiap item: {\"role\":\"coder|researcher|analyst|creative|fixer|general\",\"task\":\"...\"}. "
            f"Maksimal {runner_count} item. Roles tersedia: {', '.join(map(str, roles))}.\nTask: {task}"
        )
        try:
            response = self.provider.chat([{"role": "user", "content": prompt}])
            data = json.loads(_extract_array(response.content))
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except Exception as exc:
            print_error(self.console, f"Lead plan fallback: {exc}", self.ui_mode)
        return [{"role": roles[i % len(roles)] if roles else "general", "task": task} for i in range(runner_count)]

    def _planner_refine(self, task: str, plan: list[dict[str, str]], planner_count: int) -> list[dict[str, str]]:
        prompt = (
            f"Kamu Planner NyalaTeam ({planner_count}). Rapikan rencana berikut tanpa menambah risiko. "
            "Balas JSON array saja.\n"
            f"Task utama: {task}\nPlan: {json.dumps(plan, ensure_ascii=False)}"
        )
        try:
            response = self.provider.chat([{"role": "user", "content": prompt}])
            data = json.loads(_extract_array(response.content))
            if isinstance(data, list) and data:
                return [item for item in data if isinstance(item, dict)]
        except Exception:
            return plan
        return plan

    def _runner(self, role: str, subtask: str) -> str:
        agent = Agent(
            self.config,
            self.session,
            self.skills,
            self.platform_info,
            self.console,
            self.ui_mode,
            self.project_root,
            interactive_permissions=True,
        )
        return agent.handle(f"[NyalaTeam Runner role={role}]\n{subtask}")

    def _synthesize(self, task: str, results: list[str]) -> str:
        prompt = (
            "Kamu Lead NyalaTeam. Gabungkan hasil runner menjadi jawaban final yang jelas dan actionable.\n"
            f"Task utama: {task}\n\n"
            + "\n\n".join(results)
        )
        try:
            response = self.provider.chat([{"role": "user", "content": prompt}])
            return response.content.strip()
        except ProviderError as exc:
            return f"NyalaTeam selesai, tapi synthesis provider gagal:\n{exc.summary()}\n\n" + "\n\n".join(results)


def _extract_array(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.replace("json\n", "", 1).strip()
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped
