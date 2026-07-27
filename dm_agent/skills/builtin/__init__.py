"""内置技能注册"""

from __future__ import annotations

from dm_agent.skills.base import BaseSkill

from .db_expert import DatabaseExpertSkill
from .frontend_dev import FrontendDevSkill
from .python_expert import PythonExpertSkill


def get_builtin_skills() -> list[BaseSkill]:
    """返回所有内置技能实例列表。"""
    return [
        PythonExpertSkill(),
        DatabaseExpertSkill(),
        FrontendDevSkill(),
    ]
