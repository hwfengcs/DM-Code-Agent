"""技能管理器"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import BaseSkill, ConfigSkill
from .selector import SkillSelector

if TYPE_CHECKING:
    from ..clients.base_client import BaseLLMClient
    from ..tools.base import Tool


class SkillManager:
    """技能管理器，负责技能的注册、加载、选择和激活。

    仿照 MCPManager 模式设计。
    """

    def __init__(
        self,
        *,
        max_active_skills: int = 3,
        min_keyword_score: float = 0.05,
        enable_llm_fallback: bool = False,
        llm_client: Optional["BaseLLMClient"] = None,
    ) -> None:
        self.skills: Dict[str, BaseSkill] = {}
        self.active_skills: List[str] = []
        self._selector = SkillSelector(
            max_active_skills=max_active_skills,
            min_keyword_score=min_keyword_score,
            enable_llm_fallback=enable_llm_fallback,
            llm_client=llm_client,
        )

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def load_builtin_skills(self) -> int:
        """从 builtin 包加载内置技能，返回加载数量。"""
        from .builtin import get_builtin_skills

        count = 0
        for skill in get_builtin_skills():
            meta = skill.get_metadata()
            self.skills[meta.name] = skill
            count += 1
        return count

    def load_custom_skills(self, directory: str | Path | None = None) -> int:
        """从目录扫描 JSON 文件加载自定义技能，返回加载数量。"""
        if directory is None:
            directory = Path(__file__).parent / "custom"
        else:
            directory = Path(directory)

        if not directory.is_dir():
            return 0

        count = 0
        for json_file in sorted(directory.glob("*.json")):
            try:
                skill = ConfigSkill.from_file(json_file)
                meta = skill.get_metadata()
                self.skills[meta.name] = skill
                count += 1
            except Exception as e:
                print(f"⚠ 加载自定义技能 {json_file.name} 失败：{e}")
        return count

    def load_all(self) -> int:
        """加载全部技能（内置 + 自定义），返回总数。"""
        builtin_count = self.load_builtin_skills()
        custom_count = self.load_custom_skills()
        return builtin_count + custom_count

    # ------------------------------------------------------------------
    # 选择与激活
    # ------------------------------------------------------------------

    def select_skills_for_task(self, task: str) -> List[str]:
        """根据任务自动选择技能，返回选中的技能名称列表。"""
        return self._selector.select(task, self.skills)

    def activate_skills(self, names: List[str]) -> None:
        """激活指定技能。"""
        self.deactivate_all()
        for name in names:
            skill = self.skills.get(name)
            if skill:
                skill.on_activate()
                self.active_skills.append(name)

    def deactivate_all(self) -> None:
        """停用所有已激活的技能。"""
        for name in self.active_skills:
            skill = self.skills.get(name)
            if skill:
                skill.on_deactivate()
        self.active_skills = []

    # ------------------------------------------------------------------
    # 获取激活技能的内容
    # ------------------------------------------------------------------

    def get_active_prompt_additions(self) -> str:
        """返回所有激活技能的 prompt 合并文本。"""
        parts: List[str] = []
        for name in self.active_skills:
            skill = self.skills.get(name)
            if skill:
                addition = skill.get_prompt_addition()
                if addition:
                    meta = skill.get_metadata()
                    parts.append(f"\n\n## 专家技能：{meta.display_name}\n{addition}")
        return "".join(parts)

    def get_active_tools(self) -> List["Tool"]:
        """返回所有激活技能的工具合并列表。"""
        tools: List["Tool"] = []
        for name in self.active_skills:
            skill = self.skills.get(name)
            if skill:
                tools.extend(skill.get_tools())
        return tools

    # ------------------------------------------------------------------
    # 信息查询
    # ------------------------------------------------------------------

    def get_all_skill_info(self) -> List[Dict[str, Any]]:
        """返回所有技能摘要信息。"""
        info_list: List[Dict[str, Any]] = []
        for name, skill in self.skills.items():
            meta = skill.get_metadata()
            tools = skill.get_tools()
            info_list.append(
                {
                    "name": meta.name,
                    "display_name": meta.display_name,
                    "description": meta.description,
                    "keywords": meta.keywords,
                    "priority": meta.priority,
                    "version": meta.version,
                    "tools_count": len(tools),
                    "is_active": name in self.active_skills,
                    "is_builtin": not isinstance(skill, ConfigSkill),
                }
            )
        return info_list
