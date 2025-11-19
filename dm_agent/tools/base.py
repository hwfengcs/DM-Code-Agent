"""工具基础定义"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class Tool:
    """表示智能体可以调用的可调用工具。"""

    name: str # 工具名称
    description: str # 工具描述
    runner: Callable[[Dict[str, Any]], str] # 工具执行函数(名称能否改为function?)

    def execute(self, arguments: Dict[str, Any]) -> str:
        """
        执行工具
        """
        return self.runner(arguments)


def _require_str(arguments: Dict[str, Any], key: str) -> str:
    """
    从参数字典中提取必需的字符串参数
    
    Args:
        arguments (Dict[str, Any]): 包含参数的字典
        key (str): 要提取的参数键名
        
    Returns:
        stripped_value (str): 去除首尾空白的字符串参数值
        
    Raises:
        ValueError: 当参数不符合要求时抛出异常
            - 参数不是字典类型
            - 缺少必需的参数键
            - 参数值不是字符串类型
            - 参数值为空字符串
    """
    # 我猜,arguments在之前已经有非空判断了
    if not isinstance(arguments, dict):
        raise ValueError("参数必须是一个字典")
    
    if key not in arguments:
        raise ValueError(f"缺少必需的参数: {key}")
    
    value = arguments[key]
    if not isinstance(value, str):
        raise ValueError(f"参数 {key} 得到的{value}必须是一个字符串")
    
    stripped_value = value.strip()
    if not stripped_value:
        raise ValueError(f"参数 {key} 得到的{value}不能为空")
    
    return stripped_value
