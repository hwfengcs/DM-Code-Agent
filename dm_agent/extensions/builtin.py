"""把当前内置工具与技能适配为最低优先级扩展来源。"""

from __future__ import annotations

from .registry import ExtensionAPI


def setup_builtin_extensions(api: ExtensionAPI) -> None:
    """注册现有内置能力；后续提交会把注册职责下移到各自模块。"""
    from dm_agent.skills.builtin import get_builtin_skills
    from dm_agent.tools import default_tools

    for tool in default_tools(include_mcp=False):
        api.register_tool(tool)
    for skill in get_builtin_skills():
        api.register_skill(skill)
