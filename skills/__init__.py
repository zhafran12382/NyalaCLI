"""Built-in and generated skill registry."""

from __future__ import annotations

from .bash_exec import BashExecSkill
from .file_manager import FileManagerSkill
from .python_exec import PythonExecSkill
from .skill_creator import SkillCreatorSkill
from .web_scraper import WebScraperSkill
from .web_search import WebSearchSkill


def load_builtin_skills():
    skills = [
        FileManagerSkill(),
        BashExecSkill(),
        PythonExecSkill(),
        WebSearchSkill(),
        WebScraperSkill(),
        SkillCreatorSkill(),
    ]
    return {skill.name: skill for skill in skills}
