"""由 LLM API 驱动的 ReAct 风格智能体。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..clients.base_client import BaseLLMClient
from ..tools.base import Tool
from ..prompts import build_code_agent_prompt
from ..memory.context_compressor import ContextCompressor
from .planner import TaskPlanner, PlanStep


@dataclass
class Step:
    """表示智能体的一个推理步骤。"""

    thought: str
    action: str
    action_input: Any
    observation: str
    raw: str = ""


class ReactAgent:
    """使用 LLM 进行规划的简单 ReAct（推理+行动）智能体。"""

    def __init__(
        self,
        client: BaseLLMClient,
        tools: List[Tool],
        *,
        max_steps: int = 200,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None,
        step_callback: Optional[Callable[[int, Step], None]] = None,
        enable_planning: bool = True,
        enable_compression: bool = True,
    ) -> None:
        if not tools:
            raise ValueError("必须为 ReactAgent 提供至少一个工具。")
        self.client = client
        self.tools = {tool.name: tool for tool in tools}
        self.tools_list = tools  # 保留工具列表用于规划器
        self.max_steps = max_steps
        self.temperature = temperature
        self.system_prompt = system_prompt or build_code_agent_prompt(tools)
        self.step_callback = step_callback
        # 多轮对话历史记录
        self.conversation_history: List[Dict[str, str]] = []

        # 规划器
        self.enable_planning = enable_planning
        self.planner = TaskPlanner(client, tools) if enable_planning else None

        # 上下文压缩器（每 5 轮对话压缩一次）
        self.enable_compression = enable_compression
        self.compressor = ContextCompressor(client, compress_every=5, keep_recent=3) if enable_compression else None

    def run(self, task: str, *, max_steps: Optional[int] = None) -> Dict[str, Any]:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("任务必须是非空字符串。")

        steps: List[Step] = []
        limit = max_steps or self.max_steps

        # 第一步：生成计划（如果启用）
        plan = []
        if self.enable_planning and self.planner:
            try:
                plan = self.planner.plan(task)
                if plan:
                    plan_text = self.planner.get_progress()
                    print(f"\n📋 生成的执行计划：\n{plan_text}")
            except Exception as e:
                print(f"⚠️ 计划生成失败：{e}，将使用常规模式执行")

        # 添加新任务到对话历史
        task_prompt = self._build_user_prompt(task, steps, plan)
        self.conversation_history.append({"role": "user", "content": task_prompt})

        for step_num in range(1, limit + 1):
            # 第二步：压缩上下文（如果需要）
            messages_to_send = [{"role": "system", "content": self.system_prompt}] + self.conversation_history

            if self.enable_compression and self.compressor:
                if self.compressor.should_compress(self.conversation_history):
                    print(f"\n🗜️ 压缩对话历史以节省 token...")
                    compressed_history = self.compressor.compress(self.conversation_history)
                    messages_to_send = [{"role": "system", "content": self.system_prompt}] + compressed_history

                    # 显示压缩统计
                    stats = self.compressor.get_compression_stats(
                        self.conversation_history, compressed_history
                    )
                    print(
                        f"   压缩率：{stats['compression_ratio']:.1%}，"
                        f"节省 {stats['saved_messages']} 条消息"
                    )

            raw = self.client.respond(messages_to_send, temperature=self.temperature)

            # 将 AI 响应添加到历史记录
            self.conversation_history.append({"role": "assistant", "content": raw})
            try:
                parsed = self._parse_agent_response(raw)
            except ValueError as exc:
                observation = f"解析智能体响应失败：{exc}"
                step = Step(
                    thought="",
                    action="error",
                    action_input={},
                    observation=observation,
                    raw=raw,
                )
                steps.append(step)

                # 将错误观察添加到历史记录
                self.conversation_history.append({"role": "user", "content": f"观察：{observation}"})

                if self.step_callback:
                    self.step_callback(step_num, step)
                continue

            action = parsed.get("action", "").strip()
            thought = parsed.get("thought", "").strip()
            action_input = parsed.get("action_input")

            if action == "finish":
                final = self._format_final_answer(action_input)
                step = Step(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation="<finished>",
                    raw=raw,
                )
                steps.append(step)

                # 添加完成标记到历史记录
                self.conversation_history.append({"role": "user", "content": f"任务完成：{final}"})

                if self.step_callback:
                    self.step_callback(step_num, step)
                return {"final_answer": final, "steps": [step.__dict__ for step in steps]}

            tool = self.tools.get(action)
            if tool is None:
                observation = f"未知工具 '{action}'。"
                step = Step(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation=observation,
                    raw=raw,
                )
                steps.append(step)

                # 将观察结果添加到历史记录
                self.conversation_history.append({"role": "user", "content": f"观察：{observation}"})

                if self.step_callback:
                    self.step_callback(step_num, step)
                continue

            # task_complete 工具可以接受字符串或空参数
            if action == "task_complete":
                if action_input is None:
                    action_input = {}
                elif isinstance(action_input, str):
                    action_input = {"message": action_input}
                elif not isinstance(action_input, dict):
                    action_input = {}
                try:
                    observation = tool.execute(action_input)
                except Exception as exc:  # noqa: BLE001 - 将工具错误传递给 LLM
                    observation = f"工具执行失败：{exc}"
            elif action_input is None:
                observation = "工具参数缺失（action_input 为 null）。"
            elif not isinstance(action_input, dict):
                observation = "工具参数必须是 JSON 对象。"
            else:
                try:
                    observation = tool.execute(action_input)
                except Exception as exc:  # noqa: BLE001 - 将工具错误传递给 LLM
                    observation = f"工具执行失败：{exc}"

            step = Step(
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
                raw=raw,
            )
            steps.append(step)

            # 更新计划进度（如果有计划）
            if plan and self.planner:
                # 查找当前步骤对应的计划步骤
                for plan_step in plan:
                    if plan_step.action == action and not plan_step.completed:
                        self.planner.mark_completed(plan_step.step_number, observation)
                        break

            # 将工具执行结果添加到历史记录
            tool_info = f"执行工具 {action}，输入：{json.dumps(action_input, ensure_ascii=False)}\n观察：{observation}"
            self.conversation_history.append({"role": "user", "content": tool_info})

            # 调用回调函数实时输出步骤
            if self.step_callback:
                self.step_callback(step_num, step)

            # 检查是否调用了 task_complete 工具
            if action == "task_complete" and not observation.startswith("工具执行失败"):
                return {
                    "final_answer": observation,
                    "steps": [step.__dict__ for step in steps],
                }

        return {
            "final_answer": "达到步骤限制但未完成。",
            "steps": [step.__dict__ for step in steps],
        }

    def _build_user_prompt(self, task: str, steps: List[Step], plan: List[PlanStep] = None) -> str:
        lines = [f"任务：{task.strip()}"]

        # 如果有计划，添加到提示中
        if plan:
            lines.append("\n执行计划：")
            for plan_step in plan:
                status = "✓" if plan_step.completed else "○"
                lines.append(f"{status} 步骤 {plan_step.step_number}: {plan_step.action} - {plan_step.reason}")

        if steps:
            lines.append("\n之前的步骤：")
            for index, step in enumerate(steps, start=1):
                lines.append(f"步骤 {index} 思考：{step.thought}")
                lines.append(f"步骤 {index} 动作：{step.action}")
                lines.append(f"步骤 {index} 输入：{json.dumps(step.action_input, ensure_ascii=False)}")
                lines.append(f"步骤 {index} 观察：{step.observation}")
        lines.append(
            "\n用 JSON 对象回应：{\"thought\": string, \"action\": string, \"action_input\": object|string}。"
        )
        return "\n".join(lines)

    def _parse_agent_response(self, raw: str) -> Dict[str, Any]:
        candidate = raw.strip()
        if not candidate:
            raise ValueError("模型返回空响应。")
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("响应不是有效的 JSON。")
            snippet = candidate[start : end + 1]
            parsed = json.loads(snippet)
        if not isinstance(parsed, dict):
            raise ValueError("智能体响应的 JSON 必须是对象。")
        return parsed

    def reset_conversation(self) -> None:
        """重置对话历史"""
        self.conversation_history = []

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self.conversation_history.copy()

    @staticmethod
    def _format_final_answer(action_input: Any) -> str:
        if isinstance(action_input, str):
            return action_input
        if isinstance(action_input, dict) and "answer" in action_input:
            value = action_input["answer"]
            if isinstance(value, str):
                return value
        return json.dumps(action_input, ensure_ascii=False)