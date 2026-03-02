"""系统提示词定义"""

from pathlib import Path
from typing import List
from ..tools.base import Tool
from .code_agent_prompt import SYSTEM_PROMPT


def build_code_agent_prompt(
    tools: List[Tool], 
    formatted_references: str = "暂无参考内容"
) -> str:
    """从 markdown 文件构建 Code Agent 的系统提示词

    Args:
        tools: 可用工具列表
        formatted_references: 格式化后的参考内容字符串
    Returns:
        系统提示词字符串
    """

    # 构建工具列表
    tool_lines = "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)

    # 替换模板中的工具占位符和参考内容占位符
    return SYSTEM_PROMPT.replace("{tools}", tool_lines).replace("{formatted_references}", formatted_references)
