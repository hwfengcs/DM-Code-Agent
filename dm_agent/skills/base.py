"""技能系统基础定义"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dm_agent.tools.base import Tool


@dataclass
class SkillMetadata:
    """技能元数据"""

    name: str  # 技能唯一标识符
    display_name: str  # 显示名称
    description: str  # 技能描述
    keywords: list[str] = field(default_factory=list)  # 匹配关键词
    patterns: list[str] = field(default_factory=list)  # 正则匹配模式
    priority: int = 10  # 优先级（数值越小越高）
    version: str = "1.0.0"


class BaseSkill(ABC):
    """技能抽象基类

    所有技能必须实现 get_metadata、get_prompt_addition 和 get_tools 三个方法。
    可选实现 on_activate 和 on_deactivate 生命周期钩子。
    """

    @abstractmethod
    def get_metadata(self) -> SkillMetadata:
        """返回技能元数据"""

    @abstractmethod
    def get_prompt_addition(self) -> str:
        """返回追加到 system prompt 的文本"""

    @abstractmethod
    def get_tools(self) -> list[Tool]:
        """返回该技能提供的专用工具列表"""

    def on_activate(self) -> None:
        """技能被激活时调用（可选钩子）"""

    def on_deactivate(self) -> None:
        """技能被停用时调用（可选钩子）"""


class ConfigSkill(BaseSkill):
    """从 JSON 配置字典初始化的简单技能实现"""

    def __init__(self, config: dict[str, Any]) -> None:
        self._metadata = SkillMetadata(
            name=config["name"],
            display_name=config.get("display_name", config["name"]),
            description=config.get("description", ""),
            keywords=config.get("keywords", []),
            patterns=config.get("patterns", []),
            priority=config.get("priority", 10),
            version=config.get("version", "1.0.0"),
        )
        self._prompt_addition = config.get("prompt_addition", "")

    def get_metadata(self) -> SkillMetadata:
        return self._metadata

    def get_prompt_addition(self) -> str:
        return self._prompt_addition

    def get_tools(self) -> list[Tool]:
        # JSON 配置技能不提供自定义工具
        return []

    @classmethod
    def from_file(cls, path: str | Path) -> ConfigSkill:
        """从 JSON 文件加载技能配置"""
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
        return cls(config)
