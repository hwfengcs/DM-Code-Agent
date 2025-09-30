"""由 DeepSeek API 驱动的 ReAct 风格智能体。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .client import DeepSeekClient
from .tools import Tool


@dataclass
class Step:
    """表示智能体的一个推理步骤。"""

    thought: str
    action: str
    action_input: Any
    observation: str
    raw: str = ""


class ReactAgent:
    """使用 DeepSeek 模型进行规划的简单 ReAct（推理+行动）智能体。"""

    def __init__(
        self,
        client: DeepSeekClient,
        tools: List[Tool],
        *,
        max_steps: int = 200,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None,
    ) -> None:
        if not tools:
            raise ValueError("必须为 ReactAgent 提供至少一个工具。")
        self.client = client
        self.tools = {tool.name: tool for tool in tools}
        self.max_steps = max_steps
        self.temperature = temperature
        self.system_prompt = system_prompt or self._build_default_system_prompt(tools)

    def _build_default_system_prompt(self, tools: List[Tool]) -> str:
        tool_lines = "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)
        return (
            "你是一个谨慎的 AI 助手，使用 ReAct 模式。\n"
            "你首先需要判别用户的问题是否需要开启推理模式，如果不需要则直接回答"
            "在选择开始行动之前，你必须明确地进行推理。\n"
            "可用工具：\n"
            f"{tool_lines}\n\n"
            "当你回应时，输出一个包含 'thought'、'action' 和 'action_input' 键的 JSON 对象。\n"
            "- 'thought' 必须解释你对该步骤的推理。\n"
            "- 'action' 必须是上述工具名称之一或字面字符串 'finish'。\n"
            "- 'action_input' 在调用工具时必须是包含参数的 JSON 对象。\n"
            "- 如果你选择 'finish'，将 'action_input' 设置为最终答案字符串。\n"
            "只返回有效的 JSON，使用双引号，不要包含额外的注释。"
        )

    def run(self, task: str, *, max_steps: Optional[int] = None) -> Dict[str, Any]:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("任务必须是非空字符串。")

        steps: List[Step] = []
        limit = max_steps or self.max_steps

        for _ in range(1, limit + 1):
            prompt = self._build_user_prompt(task, steps)
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ]

            raw = self.client.respond(messages, temperature=self.temperature)
            try:
                parsed = self._parse_agent_response(raw)
            except ValueError as exc:
                observation = f"解析智能体响应失败：{exc}"
                steps.append(
                    Step(
                        thought="",
                        action="error",
                        action_input={},
                        observation=observation,
                        raw=raw,
                    )
                )
                continue

            action = parsed.get("action", "").strip()
            thought = parsed.get("thought", "").strip()
            action_input = parsed.get("action_input")

            if action == "finish":
                final = self._format_final_answer(action_input)
                steps.append(
                    Step(
                        thought=thought,
                        action=action,
                        action_input=action_input,
                        observation="<finished>",
                        raw=raw,
                    )
                )
                return {"final_answer": final, "steps": [step.__dict__ for step in steps]}

            tool = self.tools.get(action)
            if tool is None:
                observation = f"未知工具 '{action}'。"
                steps.append(
                    Step(
                        thought=thought,
                        action=action,
                        action_input=action_input,
                        observation=observation,
                        raw=raw,
                    )
                )
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

            steps.append(
                Step(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation=observation,
                    raw=raw,
                )
            )

            # 检查是否调用了 task_complete 工具
            if action == "task_complete" and not observation.startswith("工具执行失败"):
                print(f"\n调用 {action} 工具，任务全部完成\n")
                return {
                    "final_answer": observation,
                    "steps": [step.__dict__ for step in steps],
                }

        return {
            "final_answer": "达到步骤限制但未完成。",
            "steps": [step.__dict__ for step in steps],
        }

    def _build_user_prompt(self, task: str, steps: List[Step]) -> str:
        lines = [f"任务：{task.strip()}"]
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

    @staticmethod
    def _format_final_answer(action_input: Any) -> str:
        if isinstance(action_input, str):
            return action_input
        if isinstance(action_input, dict) and "answer" in action_input:
            value = action_input["answer"]
            if isinstance(value, str):
                return value
        return json.dumps(action_input, ensure_ascii=False)
