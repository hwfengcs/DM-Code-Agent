"""提示词素材装配：任务提示词与技能激活。

两者都是"发给模型的内容从哪来"：``build_user_prompt`` 决定 user 消息长什么样，
``activate_skills`` 决定本轮往 system prompt 与工具表里叠加什么。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from dm_agent.tools.base import Tool

from .planner import PlanStep
from .run_state import Step

RESPONSE_FORMAT_HINT = (
    '\n用 JSON 对象回应：{"thought": string, "action": string, "action_input": object|string}。'
)


@dataclass(frozen=True)
class SkillActivation:
    """本轮技能激活的增量：选中了哪些、要叠加什么 prompt 与工具。"""

    selected: list[str] = field(default_factory=list)
    prompt_addition: str = ""
    tools: list[Tool] = field(default_factory=list)


def build_user_prompt(
    task: str, steps: Sequence[Step], plan: Sequence[PlanStep] | None = None
) -> str:
    """构建用户提示词。

    Args:
        task: 当前任务描述
        steps: 已执行的步骤列表
        plan: 执行计划

    Returns:
        构建好的用户提示词字符串
    """
    lines: list[str] = [f"任务：{task.strip()}"]

    # 如果有计划，添加到提示中
    if plan:
        lines.append("\n执行计划：")
        for plan_step in plan:
            status = "[done]" if plan_step.completed else "[todo]"
            lines.append(
                f"{status} 步骤 {plan_step.step_number}: {plan_step.action} - {plan_step.reason}"
            )

    if steps:
        lines.append("\n之前的步骤：")
        for index, step in enumerate(steps, start=1):
            lines.append(f"步骤 {index} 思考：{step.thought}")
            lines.append(f"步骤 {index} 动作：{step.action}")
            lines.append(f"步骤 {index} 输入：{json.dumps(step.action_input, ensure_ascii=False)}")
            lines.append(f"步骤 {index} 观察：{step.observation}")
    lines.append(RESPONSE_FORMAT_HINT)
    return "\n".join(lines)


def activate_skills(manager: Any, task: str) -> SkillActivation:
    """按任务自动选择并激活技能，返回要叠加的 prompt 与工具。

    只与技能管理器打交道，不碰 agent 的 system prompt / 工具表——由调用方决定
    怎么把增量合并进去（合并前它才知道该从哪个基线出发）。
    """
    selected = manager.select_skills_for_task(task)
    if not selected:
        manager.deactivate_all()
        return SkillActivation()

    manager.activate_skills(selected)
    prompt_addition = manager.get_active_prompt_additions()
    skill_tools = list(manager.get_active_tools())

    display_names = []
    for name in selected:
        skill = manager.skills.get(name)
        if skill:
            display_names.append(skill.get_metadata().display_name)
    if display_names:
        print(f"\n[skills] 已激活技能：{', '.join(display_names)}")

    return SkillActivation(
        selected=list(selected),
        prompt_addition=prompt_addition,
        tools=skill_tools,
    )
