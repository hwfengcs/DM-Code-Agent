"""技能自动选择器"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..clients.base_client import BaseLLMClient
    from .base import BaseSkill


class SkillSelector:
    """根据任务文本自动选择最合适的技能。

    混合选择策略：
    1. 关键词匹配（默认，无额外开销）
    2. 正则模式匹配（给更高权重）
    3. LLM 辅助选择（可选，关键词无结果时触发）
    """

    def __init__(
        self,
        *,
        max_active_skills: int = 3,
        min_keyword_score: float = 0.05,
        enable_llm_fallback: bool = False,
        llm_client: Optional["BaseLLMClient"] = None,
    ) -> None:
        self.max_active_skills = max_active_skills
        self.min_keyword_score = min_keyword_score
        self.enable_llm_fallback = enable_llm_fallback
        self.llm_client = llm_client

    def select(self, task: str, skills: Dict[str, "BaseSkill"]) -> List[str]:
        """为任务选择最合适的技能，返回技能名称列表。"""
        if not skills or not task.strip():
            return []

        scored = self._score_all(task, skills)

        # 过滤低于阈值的
        candidates = [
            (name, score) for name, score in scored.items() if score >= self.min_keyword_score
        ]

        if not candidates and self.enable_llm_fallback and self.llm_client:
            candidates = self._llm_select(task, skills)

        # 按分数降序、优先级升序排列
        candidates.sort(key=lambda x: (-x[1], skills[x[0]].get_metadata().priority))

        return [name for name, _ in candidates[: self.max_active_skills]]

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _score_all(self, task: str, skills: Dict[str, "BaseSkill"]) -> Dict[str, float]:
        """计算每个技能的综合匹配分数。"""
        scores: Dict[str, float] = {}
        task_lower = task.lower()

        for name, skill in skills.items():
            meta = skill.get_metadata()
            kw_score = self._keyword_match(task_lower, meta.keywords)
            pat_score = self._pattern_match(task, meta.patterns)
            # 正则匹配给 1.5 倍权重
            scores[name] = kw_score + pat_score * 1.5

        return scores

    @staticmethod
    def _keyword_match(task_lower: str, keywords: List[str]) -> float:
        """关键词匹配，返回 0-1 之间的分数。"""
        if not keywords:
            return 0.0
        hits = sum(1 for kw in keywords if kw.lower() in task_lower)
        return hits / len(keywords)

    @staticmethod
    def _pattern_match(task: str, patterns: List[str]) -> float:
        """正则模式匹配，返回 0-1 之间的分数。"""
        if not patterns:
            return 0.0
        hits = 0
        for pat in patterns:
            try:
                if re.search(pat, task, re.IGNORECASE):
                    hits += 1
            except re.error:
                continue
        return hits / len(patterns)

    def _llm_select(self, task: str, skills: Dict[str, "BaseSkill"]) -> List[tuple]:
        """使用 LLM 辅助选择技能（备用策略）。"""
        if not self.llm_client:
            return []

        skill_descriptions = "\n".join(
            f"- {name}: {skill.get_metadata().description}" for name, skill in skills.items()
        )
        prompt = (
            f"根据以下任务描述，从可用技能列表中选择最相关的技能（最多 {self.max_active_skills} 个）。\n"
            f"只返回技能名称，用逗号分隔，不要其他内容。\n\n"
            f"任务：{task}\n\n"
            f"可用技能：\n{skill_descriptions}"
        )

        try:
            messages = [
                {"role": "system", "content": "你是一个技能选择助手。只返回技能名称列表。"},
                {"role": "user", "content": prompt},
            ]
            response = self.llm_client.respond(messages, temperature=0.0)
            selected_names = [n.strip() for n in response.split(",") if n.strip()]
            return [(name, 1.0) for name in selected_names if name in skills]
        except Exception:
            return []
