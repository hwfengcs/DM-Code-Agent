"""任务规划器 - 生成和管理任务执行计划"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..clients.base_client import BaseLLMClient
from ..tools.base import Tool


@dataclass
class PlanStep:
    """计划中的单个步骤"""

    step_number: int
    action: str
    reason: str
    completed: bool = False
    result: Optional[str] = None


class TaskPlanner:
    """任务规划器：在执行前生成全局计划"""

    def __init__(self, client: BaseLLMClient, tools: List[Tool]):
        self.client = client
        self.tools = tools
        self.current_plan: List[PlanStep] = []

    def plan(self, task: str) -> List[PlanStep]:
        """
        为任务生成执行计划

        Args:
            task: 任务描述

        Returns:
            计划步骤列表
        """
        # 构建工具描述
        tool_descriptions = "\n".join(
            [f"- {tool.name}: {tool.description}" for tool in self.tools]
        )

        prompt = f"""你是一个专业的任务规划助手。请为以下任务生成详细的执行计划。

任务：{task}

可用工具：
{tool_descriptions}

请生成一个结构化的执行计划，包含 3-8 个步骤。每个步骤应该：
1. 使用可用的工具
2. 有明确的目的
3. 按逻辑顺序排列
4. 能够独立验证

返回 JSON 格式：
{{
  "plan": [
    {{"step": 1, "action": "工具名称", "reason": "为什么需要这一步"}},
    {{"step": 2, "action": "工具名称", "reason": "为什么需要这一步"}},
    ...
  ]
}}

注意：
- action 必须是可用工具列表中的工具名称
- 最后一步应该是 "task_complete"
- 保持计划简洁高效，避免不必要的步骤
"""

        messages = [{"role": "user", "content": prompt}]
        response = self.client.respond(messages, temperature=0.3)

        # 解析计划
        try:
            plan_data = self._parse_plan_response(response)
            steps = []
            for item in plan_data.get("plan", []):
                steps.append(
                    PlanStep(
                        step_number=item["step"],
                        action=item["action"],
                        reason=item["reason"],
                    )
                )
            self.current_plan = steps
            return steps
        except Exception as e:
            # 如果解析失败，返回空计划（回退到逐步执行模式）
            print(f"警告：计划生成失败 - {e}，将使用逐步执行模式")
            return []

    def _parse_plan_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 返回的计划"""
        # 尝试直接解析
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            # 尝试提取 JSON
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end != -1:
                json_str = response[start : end + 1]
                return json.loads(json_str)
            raise ValueError("无法解析计划响应")

    def mark_completed(self, step_number: int, result: str) -> None:
        """标记步骤为完成"""
        for step in self.current_plan:
            if step.step_number == step_number:
                step.completed = True
                step.result = result
                break

    def get_next_step(self) -> Optional[PlanStep]:
        """获取下一个未完成的步骤"""
        for step in self.current_plan:
            if not step.completed:
                return step
        return None

    def get_progress(self) -> str:
        """获取计划执行进度"""
        if not self.current_plan:
            return "无计划"

        completed = sum(1 for step in self.current_plan if step.completed)
        total = len(self.current_plan)

        progress_text = f"计划进度：{completed}/{total} 步骤已完成\n\n"
        for step in self.current_plan:
            status = "✓" if step.completed else "○"
            progress_text += f"{status} 步骤 {step.step_number}: {step.action} - {step.reason}\n"
            if step.completed and step.result:
                progress_text += f"   结果：{step.result[:100]}...\n"

        return progress_text

    def replan(
        self, task: str, completed_steps: List[PlanStep], error: Optional[str] = None
    ) -> List[PlanStep]:
        """
        遇到问题时重新规划

        Args:
            task: 原始任务
            completed_steps: 已完成的步骤
            error: 错误信息（如果有）

        Returns:
            新的计划
        """
        completed_summary = "\n".join(
            [
                f"步骤 {s.step_number}: {s.action} - {s.reason} (已完成)"
                for s in completed_steps
            ]
        )

        error_info = f"\n遇到错误：{error}" if error else ""

        prompt = f"""任务执行遇到问题，需要重新规划。

原始任务：{task}

已完成的步骤：
{completed_summary}
{error_info}

请生成新的执行计划，继续完成剩余任务。返回 JSON 格式：
{{
  "plan": [
    {{"step": 1, "action": "工具名称", "reason": "为什么需要这一步"}},
    ...
  ]
}}
"""

        messages = [{"role": "user", "content": prompt}]
        response = self.client.respond(messages, temperature=0.3)

        try:
            plan_data = self._parse_plan_response(response)
            steps = []
            for item in plan_data.get("plan", []):
                steps.append(
                    PlanStep(
                        step_number=item["step"],
                        action=item["action"],
                        reason=item["reason"],
                    )
                )
            self.current_plan = steps
            return steps
        except Exception as e:
            print(f"警告：重新规划失败 - {e}")
            return []

    def has_plan(self) -> bool:
        """是否有活跃的计划"""
        return len(self.current_plan) > 0

    def clear_plan(self) -> None:
        """清空当前计划"""
        self.current_plan = []