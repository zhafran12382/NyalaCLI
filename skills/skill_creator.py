from __future__ import annotations

import re
from typing import Any

from core.permissions import PermissionManager, safe_path_display

from .base import SkillResult


class SkillCreatorSkill:
    name = "skill_creator"
    description = "Buat template skill Python baru di generated_skills. Skill baru tidak otomatis dieksekusi."
    parameters_schema = {"name": "Nama skill snake_case.", "description": "Deskripsi singkat."}

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
        raw_name = str(args.get("name", "")).strip().lower()
        description = str(args.get("description", "Generated NyalaCLI skill.")).strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", raw_name):
            return SkillResult(False, "Nama skill harus snake_case, 3-40 karakter.")
        root = context["project_root"] / "generated_skills"
        path = root / f"{raw_name}.py"
        permission: PermissionManager = context["permission"]
        console = context.get("console")
        decision = permission.check_file("write", path)
        if not permission.confirm_if_needed(decision, f"Buat generated skill {raw_name}?", console):
            return SkillResult(False, "Pembuatan skill dibatalkan.")
        if path.exists():
            return SkillResult(False, f"Skill sudah ada: {safe_path_display(path)}")
        root.mkdir(parents=True, exist_ok=True)
        safe_description = description.replace("\\", "\\\\").replace('"', '\\"')
        template = f'''from __future__ import annotations

from skills.base import SkillResult


class GeneratedSkill:
    name = "{raw_name}"
    description = "{safe_description}"
    parameters_schema = {{"input": "Teks input."}}

    def run(self, args, context):
        value = str(args.get("input", ""))
        return SkillResult(True, f"{raw_name} menerima: {{value}}")
'''
        path.write_text(template, encoding="utf-8")
        return SkillResult(True, f"Skill dibuat: {safe_path_display(path)}\nReview manual sebelum mengaktifkan.")
