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

    step_number: int  # 步骤编号
    action: str  # 工具名称
    reason: str  # 使用工具的原因
    completed: bool = False  # 是否完成当前步骤
    result: Optional[str] = None  # 返回结果


@dataclass(frozen=True)
class ReplanSignal:
    """Structured error signal used by adaptive replanning."""

    kind: str
    strategy: str
    message: str
    severity: str = "medium"
    action: str = ""
    step_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "strategy": self.strategy,
            "message": self.message,
            "severity": self.severity,
            "action": self.action,
            "step_number": self.step_number,
        }


@dataclass(frozen=True)
class ReplanDecision:
    """Decision made before invoking the LLM planner again."""

    should_replan: bool
    strategy: str
    reason: str
    signal: ReplanSignal

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_replan": self.should_replan,
            "strategy": self.strategy,
            "reason": self.reason,
            "signal": self.signal.to_dict(),
        }


class AdaptiveReplanPolicy:
    """Deterministic policy that maps failure observations to replan strategies."""

    STRATEGIES = {
        "tool_error": "simplify_plan_skip_failed_tool",
        "unknown_tool": "select_available_tool",
        "parse_error": "repair_response_format",
        "invalid_arguments": "repair_tool_arguments",
        "test_failure": "inject_test_failure_context",
        "critic_rejected": "address_critic_feedback",
        "max_steps": "coarsen_plan_after_budget",
        "unknown": "continue_with_failure_context",
    }

    def classify(
        self,
        observation: str,
        *,
        action: str = "",
        step_number: Optional[int] = None,
        error_kind: Optional[str] = None,
    ) -> ReplanSignal:
        text = str(observation or "")
        lowered = text.lower()
        kind = error_kind or "unknown"

        if kind == "unknown":
            if "agent response parse failed" in lowered or "valid json" in lowered:
                kind = "parse_error"
            elif "unknown tool" in lowered:
                kind = "unknown_tool"
            elif "tool arguments" in lowered:
                kind = "invalid_arguments"
            elif "critic rejected" in lowered or "critic review failed" in lowered:
                kind = "critic_rejected"
            elif "tool execution failed" in lowered or "traceback" in lowered or "error" in text:
                kind = "tool_error"
            elif (
                "pytest" in lowered
                or "assertionerror" in lowered
                or "returncode: 1" in lowered
                or "failed" in lowered
            ):
                kind = "test_failure"
            elif "max steps" in lowered or "step limit" in lowered:
                kind = "max_steps"

        strategy = self.STRATEGIES.get(kind, self.STRATEGIES["unknown"])
        severity = "low" if kind == "unknown" else "medium"
        if kind in {"tool_error", "test_failure", "critic_rejected", "max_steps"}:
            severity = "high"
        return ReplanSignal(
            kind=kind,
            strategy=strategy,
            message=_compact_message(text),
            severity=severity,
            action=action,
            step_number=step_number,
        )

    def decide(
        self,
        signal: ReplanSignal,
        *,
        replan_count: int,
        max_replans: int,
    ) -> ReplanDecision:
        if max_replans >= 0 and replan_count >= max_replans:
            return ReplanDecision(
                should_replan=False,
                strategy="replan_budget_exhausted",
                reason=f"Replan budget exhausted ({replan_count}/{max_replans}).",
                signal=signal,
            )
        if signal.kind == "unknown" and signal.severity == "low":
            return ReplanDecision(
                should_replan=False,
                strategy="skip_low_confidence_signal",
                reason="Failure signal is too weak to justify another planning call.",
                signal=signal,
            )
        return ReplanDecision(
            should_replan=True,
            strategy=signal.strategy,
            reason=f"Adaptive replanning selected strategy: {signal.strategy}.",
            signal=signal,
        )


def _compact_message(text: str, *, limit: int = 500) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def normalize_replan_signal(
    error_signal: Any, fallback_error: Optional[str] = None
) -> ReplanSignal:
    """Coerce caller-provided error metadata into a ReplanSignal."""

    if isinstance(error_signal, ReplanSignal):
        return error_signal
    if isinstance(error_signal, dict):
        kind = str(error_signal.get("kind") or "unknown")
        strategy = str(
            error_signal.get("strategy")
            or AdaptiveReplanPolicy.STRATEGIES.get(kind, AdaptiveReplanPolicy.STRATEGIES["unknown"])
        )
        return ReplanSignal(
            kind=kind,
            strategy=strategy,
            message=_compact_message(str(error_signal.get("message") or fallback_error or "")),
            severity=str(error_signal.get("severity") or "medium"),
            action=str(error_signal.get("action") or ""),
            step_number=error_signal.get("step_number"),
        )
    policy = AdaptiveReplanPolicy()
    return policy.classify(str(error_signal or fallback_error or ""))


class TaskPlanner:
    """任务规划器：在执行前生成全局计划"""

    def __init__(self, client: BaseLLMClient, tools: List[Tool]):
        self.client = client
        self.tools = tools
        self.current_plan: List[PlanStep] = []  # 当前计划列表

    def plan(self, task: str) -> List[PlanStep]:
        """
        为任务生成执行计划

        该方法通过调用大语言模型(LLM)来分析任务描述，并基于可用工具生成一个结构化的执行计划。
        计划由一系列有序的步骤组成，每个步骤都指定了要使用的工具及其理由。

        Args:
            task (str): 需要执行的任务描述字符串

        Returns:
            steps (List[PlanStep]): 包含计划步骤的列表，每个步骤是一个PlanStep对象。
                          如果计划生成失败，则返回空列表，系统将回退到逐步执行模式。

        Examples:
            >>> planner = TaskPlanner(client, tools)
            >>> steps = planner.plan("分析项目代码并生成报告")
            >>> print(len(steps))
            5
            >>> print(steps[0].action)
            'read_file'

        Raises:
            Exception: 当LLM响应解析失败时会打印警告信息，但不会抛出异常，
                      而是返回空列表以启用回退机制
        """
        # 构建工具描述
        tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])

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
        # 发送请求并获得client端的响应
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
        """
        解析 LLM 返回的计划

        Args:
            response (str): LLM 返回的 JSON 字符串

        Returns:
            解析后的 JSON 数据

        Raises:
            ValueError: 如果无法解析 JSON
        """
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
        """
        标记指定步骤为完成状态

        在任务执行过程中，当某个步骤执行完毕后，调用此方法将该步骤标记为已完成，
        并保存执行结果。

        Args:
            step_number (int): 要标记为完成的步骤编号
            result (str): 步骤执行的结果描述

        Returns:
            None: 该方法不返回任何值，直接修改内部状态

        Examples:
            >>> planner.mark_completed(1, "成功读取文件内容")
            >>> step = planner.get_next_step()
            >>> print(step.step_number)  # 假设步骤1已完成，可能返回步骤2
            2
        """
        for step in self.current_plan:
            if step.step_number == step_number:
                step.completed = True
                step.result = result
                break

    def get_next_step(self) -> Optional[PlanStep]:
        """
        获取下一个未完成的步骤

        按照步骤编号顺序查找第一个尚未完成的步骤。

        Returns:
            Optional[PlanStep]: 下一个未完成的步骤对象，如果没有未完成的步骤则返回None

        Examples:
            >>> step = planner.get_next_step()
            >>> if step:
            ...     print(f"下一步执行: {step.action}")
            ... else:
            ...     print("所有步骤已完成")
            下一步执行: read_file
        """
        for step in self.current_plan:
            if not step.completed:
                return step
        return None

    def get_progress(self) -> str:
        """
        获取计划执行进度报告

        生成一个格式化的字符串，展示当前计划的执行进度，包括已完成和未完成的步骤。

        Returns:
            progress_text (str): 格式化的进度报告字符串

        Examples:
            >>> progress = planner.get_progress()
            >>> print(progress)
            计划进度：2/5 步骤已完成
            ✓ 步骤 1: read_file - 读取项目结构
               结果：成功读取...
            ✓ 步骤 2: analyze_code - 分析代码质量
               结果：发现3个问题...
            ○ 步骤 3: fix_issues - 修复发现的问题
            ○ 步骤 4: test_fixes - 测试修复效果
            ○ 步骤 5: task_complete - 完成任务
        """
        if not self.current_plan:
            return "无计划"

        # 已完成的步骤数和总步骤数
        completed = sum(1 for step in self.current_plan if step.completed)
        total = len(self.current_plan)

        # 生成文本
        progress_text = f"计划进度：{completed}/{total} 步骤已完成\n\n"
        for step in self.current_plan:
            status = "✓" if step.completed else "○"
            progress_text += f"{status} 步骤 {step.step_number}: {step.action} - {step.reason}\n"
            if step.completed and step.result:
                progress_text += f"   结果：{step.result[:100]}...\n"

        return progress_text

    def replan(
        self,
        task: str,
        completed_steps: List[PlanStep],
        error: Optional[str] = None,
        *,
        error_signal: Any = None,
    ) -> List[PlanStep]:
        """
        遇到问题时重新规划

        当任务执行过程中出现错误时，基于已完成的步骤和错误信息重新生成执行计划。
        这种机制提高了系统的容错能力和适应性。

        Args:
            task (str): 原始任务描述
            completed_steps (List[PlanStep]): 已成功完成的步骤列表
            error (Optional[str], optional): 错误信息描述，默认为None

        Returns:
            steps (List[PlanStep]): 新生成的计划步骤列表，如果重新规划失败则返回空列表

        Examples:
            >>> completed = [step for step in planner.current_plan if step.completed]
            >>> error_msg = "文件不存在: config.json"
            >>> new_plan = planner.replan("分析项目配置", completed, error_msg)
            >>> if new_plan:
            ...     print(f"重新规划了{len(new_plan)}个步骤")
            ... else:
            ...     print("重新规划失败")
        """
        completed_summary = "\n".join(
            [f"步骤 {s.step_number}: {s.action} - {s.reason} (已完成)" for s in completed_steps]
        )

        error_info = f"\n{error}" if error else ""
        signal = normalize_replan_signal(error_signal, fallback_error=error)
        strategy_guidance = _strategy_guidance(signal)

        prompt = f"""任务执行遇到问题，需要重新规划。

原始任务：{task}

已完成的步骤：
{completed_summary}
错误信息：
{error_info}

错误信号：
- kind: {signal.kind}
- strategy: {signal.strategy}
- severity: {signal.severity}
- action: {signal.action or "unknown"}

策略提示：
{strategy_guidance}

请生成新的执行计划，继续完成剩余任务。返回 JSON 格式：
{{
  "plan": [
    {{"step": 1, "action": "工具名称", "reason": "为什么需要这一步"}},
    ...
  ]
}}
"""
        # 流程类似plan()
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
        """
        检查是否存在活跃的计划

        Returns:
            bool: 如果存在未完成的计划步骤则返回True，否则返回False

        Examples:
            >>> if planner.has_plan():
            ...     print("继续执行计划...")
            ... else:
            ...     print("等待新任务...")
        """
        return len(self.current_plan) > 0

    def clear_plan(self) -> None:
        """
        清空当前计划

        将当前计划重置为空列表，清除所有已有的计划步骤。

        Returns:
            None: 该方法不返回任何值

        Examples:
            >>> planner.clear_plan()
            >>> print(planner.has_plan())
            False
        """
        self.current_plan = []


def _strategy_guidance(signal: ReplanSignal) -> str:
    guidance = {
        "tool_error": (
            "Simplify the next plan, avoid repeating the failed tool call blindly, "
            "and inspect the concrete error before retrying."
        ),
        "unknown_tool": (
            "Use only tools listed in the available tool set; replace unavailable tools "
            "with the closest supported inspection or edit action."
        ),
        "parse_error": (
            "Add an explicit response-format checkpoint. The next agent step must return "
            "a strict JSON object with thought/action/action_input."
        ),
        "invalid_arguments": (
            "Repair the tool argument shape before using the tool again; action_input must "
            "match the target tool schema."
        ),
        "test_failure": (
            "Inject the failing test output into the next plan and prioritize a small "
            "behavioral fix over broad refactors."
        ),
        "critic_rejected": (
            "Treat the critic feedback as a review blocker and add a concrete verification "
            "step before finishing again."
        ),
        "max_steps": (
            "Coarsen the plan: merge low-value inspection steps and move directly toward "
            "the smallest verifiable fix."
        ),
    }
    return guidance.get(
        signal.kind,
        "Continue with the failure context, but keep the new plan short and directly verifiable.",
    )
