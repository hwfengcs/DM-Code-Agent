"""内置技能注册"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dm_agent.skills.base import BaseSkill

from .db_expert import DatabaseExpertSkill
from .frontend_dev import FrontendDevSkill
from .python_expert import PythonExpertSkill

if TYPE_CHECKING:
    from dm_agent.extensions import ExtensionAPI


def get_builtin_skills() -> list[BaseSkill]:
    """返回所有内置技能实例列表，保留现有公共兼容接口。"""
    return [
        PythonExpertSkill(),
        DatabaseExpertSkill(),
        FrontendDevSkill(),
    ]


def register_builtin_skills(api: ExtensionAPI) -> None:
    """通过 ExtensionAPI 注册全部内置技能。"""
    for skill in get_builtin_skills():
        api.register_skill(skill)
