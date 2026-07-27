"""汇总最低优先级的内置扩展注册函数。"""

from __future__ import annotations

from .registry import ExtensionAPI


def setup_builtin_extensions(api: ExtensionAPI) -> None:
    """通过与第三方相同的 ExtensionAPI 注册内置能力。"""
    from dm_agent.skills.builtin import register_builtin_skills
    from dm_agent.tools import register_builtin_tools

    register_builtin_tools(api)
    register_builtin_skills(api)
