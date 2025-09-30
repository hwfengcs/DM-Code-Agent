"""工具基础定义"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class Tool:
    """表示智能体可以调用的可调用工具。"""

    name: str
    description: str
    runner: Callable[[Dict[str, Any]], str]

    def execute(self, arguments: Dict[str, Any]) -> str:
        return self.runner(arguments)


def _require_str(arguments: Dict[str, Any], key: str) -> str:
    """从参数字典中提取必需的字符串参数"""
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"工具参数 '{key}' 必须是非空字符串。")
    return value.strip()