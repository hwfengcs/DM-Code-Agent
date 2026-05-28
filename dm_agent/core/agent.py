"""由 LLM API 驱动的 ReAct 风格智能体。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..clients.base_client import BaseLLMClient
from ..tools.base import Tool
from ..prompts import build_code_agent_prompt
from ..memory.context_compressor import ContextCompressor
from .critic import CriticAgent, CriticReview
from .planner import AdaptiveReplanPolicy, PlanStep, TaskPlanner
from .reflexion import EpisodicMemory, Reflector


@dataclass
class Step:
    """表示智能体的一个推理步骤。"""

    thought: str  # 智能体的思考过程
    action: str  # 要执行的动作/工具名称
    action_input: Any  # 动作的输入参数
    observation: str  # 执行动作后的观察结果
    raw: str = ""  # 原始响应内容


class ReactAgent:
    """
    ReAct Agent 实现了推理(Reasoning)和行动(Action)的循环模式，允许智能体通过与环境交互来解决问题。
    它结合了任务规划、上下文压缩等功能，提供了一个完整的智能体执行框架。

    Attributes:
        client (BaseLLMClient): 用于与大语言模型通信的客户端
        tools (Dict[str, Tool]): 可用工具的字典映射，键为工具名称
        tools_list (List[Tool]): 工具列表，用于规划器初始化
        max_steps (int): 最大执行步骤数
        temperature (float): LLM生成文本的温度参数
        system_prompt (str): 系统提示词
        step_callback (Optional[Callable[[int, Step], None]]): 步骤执行回调函数
        enable_planning (bool): 是否启用任务规划功能
        enable_compression (bool): 是否启用上下文压缩功能
        conversation_history (List[Dict[str, str]]): 对话历史记录
        planner (Optional[TaskPlanner]): 任务规划器实例
        compressor (Optional[ContextCompressor]): 上下文压缩器实例
    """

    def __init__(
        self,
        client: BaseLLMClient,
        tools: List[Tool],
        *,
        max_steps: int = 200,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None,
        step_callback: Optional[Callable[[int, Step], None]] = None,  # 步骤回调函数
        enable_planning: bool = True,  # 是否启用规划
        enable_compression: bool = True,  # 是否启用上下文压缩
        skill_manager: Optional[Any] = None,  # 技能管理器
        trace_writer: Optional[Any] = None,
        enable_reflexion: bool = False,
        max_trials: int = 3,
        reflector: Optional[Reflector] = None,
        reflexion_memory: Optional[EpisodicMemory] = None,
        critic: Optional[CriticAgent] = None,
        enable_adaptive_replanning: bool = False,
        replan_policy: Optional[AdaptiveReplanPolicy] = None,
        max_replans: int = -1,
        enable_repeated_failure_policy_experiment: bool = False,
    ) -> None:
        """
        初始化 ReactAgent 实例

        Args:
            client (BaseLLMClient): LLM客户端实例
            tools (List[Tool]): 可用工具列表
            max_steps (int, optional): 最大执行步骤数，默认为200
            temperature (float, optional): LLM生成文本的温度参数，默认为0.0
            system_prompt (Optional[str], optional): 系统提示词，默认为None，将使用默认构建的提示词
            step_callback (Optional[Callable[[int, Step], None]], optional):
                步骤执行回调函数，可用于实时监控执行过程，默认为None
            enable_planning (bool, optional): 是否启用任务规划功能，默认为True
            enable_compression (bool, optional): 是否启用上下文压缩功能，默认为True

        Raises:
            ValueError: 当提供的工具列表为空时抛出异常

        Examples:
            >>> from dm_agent.clients import OpenAIClient
            >>> from dm_agent.tools import default_tools
            >>>
            >>> client = OpenAIClient(api_key="your-api-key")
            >>> tools = default_tools()
            >>> agent = ReactAgent(client, tools, max_steps=50)
            >>> result = agent.run("分析项目代码结构")
        """
        if not tools:
            raise ValueError("必须为 ReactAgent 提供至少一个工具。")
        if max_trials < 1:
            raise ValueError("max_trials must be at least 1.")
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
        self.compressor = (
            ContextCompressor(client, compress_every=5, keep_recent=3)
            if enable_compression
            else None
        )

        # 技能管理器
        self.skill_manager = skill_manager
        self.trace_writer = trace_writer
        self._base_system_prompt = self.system_prompt
        self._base_tools = dict(self.tools)
        self._last_parse_repaired = False
        self.enable_reflexion = enable_reflexion
        self.max_trials = max_trials
        self.reflexion_memory = reflexion_memory or EpisodicMemory()
        self.reflector = reflector or (Reflector(client) if enable_reflexion else None)
        self.critic = critic
        self.enable_adaptive_replanning = enable_adaptive_replanning
        self.replan_policy = replan_policy or AdaptiveReplanPolicy()
        self.max_replans = max_replans
        self.enable_repeated_failure_policy_experiment = enable_repeated_failure_policy_experiment

    def run(self, task: str, *, max_steps: Optional[int] = None) -> Dict[str, Any]:
        """Execute a task, optionally retrying failed trials with Reflexion."""
        if not self.enable_reflexion:
            return self._run_once(task, max_steps=max_steps)
        return self._run_with_reflexion(task, max_steps=max_steps)

    def _run_with_reflexion(
        self,
        task: str,
        *,
        max_steps: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("任务必须是非空字符串。")

        trial_limit = self.max_trials
        initial_history = [dict(message) for message in self.conversation_history]
        trial_summaries: List[Dict[str, Any]] = []
        last_result: Optional[Dict[str, Any]] = None

        for trial in range(1, trial_limit + 1):
            self.conversation_history = [dict(message) for message in initial_history]
            lesson_prompt = self.reflexion_memory.render_for_prompt()
            if self.trace_writer:
                self.trace_writer.record(
                    "trial_start",
                    {
                        "trial": trial,
                        "max_trials": trial_limit,
                        "lesson_count": len(self.reflexion_memory),
                    },
                )

            result = self._run_once(
                task,
                max_steps=max_steps,
                trial_number=trial,
                max_trials=trial_limit,
                reflexion_prompt=lesson_prompt,
            )
            metadata = result.get("metadata", {})
            summary = self._trial_summary(result, trial)
            trial_summaries.append(summary)
            metadata["trials"] = list(trial_summaries)
            metadata["trial_count"] = trial
            metadata["reflexion_lesson_count"] = len(self.reflexion_memory)
            last_result = result

            if self.trace_writer:
                self.trace_writer.record("trial_end", summary)

            if metadata.get("status") == "success":
                return result
            if trial >= trial_limit:
                return result

            lesson = self._reflect_after_failed_trial(task, result, trial)
            self.reflexion_memory.add(
                lesson,
                source="agent_failure",
                metadata={
                    "trial": trial,
                    "status": metadata.get("status"),
                    "failure_reason": metadata.get("failure_reason", ""),
                },
            )
            metadata["reflexion_lesson_count"] = len(self.reflexion_memory)
            if self.trace_writer:
                self.trace_writer.record(
                    "reflexion",
                    {
                        "trial": trial,
                        "lesson": lesson,
                        "lesson_count": len(self.reflexion_memory),
                    },
                )

        assert last_result is not None
        return last_result

    def _reflect_after_failed_trial(
        self,
        task: str,
        result: Dict[str, Any],
        trial: int,
        *,
        failure_feedback: Optional[str] = None,
    ) -> str:
        metadata = result.get("metadata", {})
        if self.reflector is None:
            return self._fallback_lesson(metadata)
        try:
            return self.reflector.reflect(
                task=task,
                final_answer=str(result.get("final_answer", "")),
                metadata=metadata,
                steps=result.get("steps", []),
                failure_feedback=failure_feedback,
            )
        except Exception as exc:  # noqa: BLE001 - reflection should not hide the prior result
            metadata["reflexion_error"] = f"trial {trial}: {exc}"
            return self._fallback_lesson(metadata)

    @staticmethod
    def _fallback_lesson(metadata: Dict[str, Any]) -> str:
        reason = metadata.get("failure_reason") or metadata.get("status") or "unknown failure"
        return (
            f"Previous trial failed with {reason}. Inspect the concrete failure signal first, "
            "then make a smaller targeted change before finishing."
        )

    @staticmethod
    def _trial_summary(result: Dict[str, Any], trial: int) -> Dict[str, Any]:
        metadata = result.get("metadata", {})
        return {
            "trial": trial,
            "status": metadata.get("status"),
            "failure_reason": metadata.get("failure_reason", ""),
            "steps": len(result.get("steps", [])),
            "final_answer_chars": len(str(result.get("final_answer", ""))),
        }

    def _run_once(
        self,
        task: str,
        *,
        max_steps: Optional[int] = None,
        trial_number: int = 1,
        max_trials: int = 1,
        reflexion_prompt: str = "",
    ) -> Dict[str, Any]:
        """
        执行指定任务

        该方法实现了完整的ReAct循环，包括任务规划、推理、行动和观察等阶段。它支持上下文压缩以
        控制token消耗，并提供回调机制用于监控执行过程。

        Args:
            task (str): 要执行的任务描述
            max_steps (Optional[int], optional): 覆盖默认的最大步骤数

        Returns:
            result (Dict[str, Any]): 包含最终答案和执行步骤的字典
                    - final_answer (str): 任务执行的最终结果
                    - steps (List[Dict]): 执行的所有步骤信息列表

        Raises:
            ValueError: 当任务不是非空字符串时抛出异常

        Examples:
            >>> result = agent.run("帮我分析项目的代码结构")
            >>> print(result["final_answer"])
            '已成功分析项目代码结构...'
        """
        if not isinstance(task, str) or not task.strip():
            raise ValueError("任务必须是非空字符串。")

        if self.enable_reflexion or reflexion_prompt:
            self.system_prompt = self._base_system_prompt
            self.tools = dict(self._base_tools)

        started_at = time.perf_counter()
        steps: List[Step] = []
        limit = max_steps or self.max_steps
        metadata: Dict[str, Any] = {
            "status": "running",
            "planning_enabled": self.enable_planning,
            "compression_enabled": self.enable_compression,
            "skills_enabled": bool(self.skill_manager),
            "activated_skills": [],
            "initial_plan_steps": 0,
            "parse_error_count": 0,
            "parse_repair_count": 0,
            "tool_error_count": 0,
            "unknown_tool_count": 0,
            "argument_error_count": 0,
            "replan_count": 0,
            "compressed_messages": 0,
            "memory_items": 0,
            "memory_injection_count": 0,
            "failure_reason": "",
            "reflexion_enabled": self.enable_reflexion,
            "critic_enabled": self.critic is not None,
            "critic_review_count": 0,
            "critic_pass_count": 0,
            "critic_fail_count": 0,
            "critic_reject_count": 0,
            "adaptive_replanning_enabled": self.enable_adaptive_replanning,
            "max_replans": self.max_replans,
            "replan_decision_count": 0,
            "replan_skipped_count": 0,
            "replan_maxed_count": 0,
            "replan_strategy": "",
            "replan_strategy_counts": {},
            "replan_signals": [],
            "last_failure_signature": "",
            "repeated_failure_count": 0,
            "repeated_failures": [],
            "repeated_failure_policy_experiment_enabled": (
                self.enable_repeated_failure_policy_experiment
            ),
            "repeated_failure_policy_applied_count": 0,
            "trial": trial_number,
            "max_trials": max_trials,
            "reflexion_lesson_count": len(self.reflexion_memory),
        }
        if self.trace_writer:
            self.trace_writer.start_run(
                task,
                metadata={
                    "max_steps": limit,
                    "temperature": self.temperature,
                    "planning_enabled": self.enable_planning,
                    "compression_enabled": self.enable_compression,
                    "skills_enabled": bool(self.skill_manager),
                    "reflexion_enabled": self.enable_reflexion,
                    "critic_enabled": self.critic is not None,
                    "adaptive_replanning_enabled": self.enable_adaptive_replanning,
                    "max_replans": self.max_replans,
                    "repeated_failure_policy_experiment_enabled": (
                        self.enable_repeated_failure_policy_experiment
                    ),
                    "trial": trial_number,
                    "max_trials": max_trials,
                    "reflexion_lesson_count": len(self.reflexion_memory),
                    "tools": [
                        {"name": tool.name, "description": tool.description}
                        for tool in self.tools_list
                    ],
                },
            )

        def finish_result(final_answer: str) -> Dict[str, Any]:
            result = {
                "final_answer": final_answer,
                "steps": [step.__dict__ for step in steps],
                "metadata": metadata,
            }
            if self.trace_writer:
                self.trace_writer.finish_run(result)
            return result

        # 技能自动选择
        if self.skill_manager:
            metadata["activated_skills"] = self._apply_skills_for_task(task)
            if self.trace_writer:
                self.trace_writer.record_skills(metadata["activated_skills"])
        if reflexion_prompt:
            self.system_prompt += "\n\n" + reflexion_prompt

        # 第一步：生成计划（如果启用）
        plan: List[PlanStep] = []
        if self.enable_planning and self.planner:
            try:
                plan = self.planner.plan(task)
                metadata["initial_plan_steps"] = len(plan)
                if self.trace_writer:
                    self.trace_writer.record_plan(plan)
                if plan:
                    plan_text = self.planner.get_progress()
                    print(f"\n[plan] 生成的执行计划：\n{plan_text}")
            except Exception as e:
                if self.trace_writer:
                    self.trace_writer.record_plan_error(str(e))
                print(f"[warn] 计划生成失败：{e}，将使用常规模式执行")

        # 添加新任务到对话历史
        task_prompt: str = self._build_user_prompt(task, steps, plan)
        self.conversation_history.append({"role": "user", "content": task_prompt})

        for step_num in range(1, limit + 1):
            # 第二步：整理旧上下文为本地记忆（如果需要）
            system_content = self.system_prompt
            messages_to_send = [
                {"role": "system", "content": system_content}
            ] + self.conversation_history

            if self.enable_compression and self.compressor:
                if self.compressor.should_compress(self.conversation_history):
                    print("\n[memory] 整理旧对话为本地原子记忆，并召回相关记忆...")
                    compressed_history = self.compressor.compress(self.conversation_history)
                    messages_to_send = [
                        {"role": "system", "content": system_content}
                    ] + compressed_history

                    # 显示压缩统计
                    stats = self.compressor.get_compression_stats(
                        self.conversation_history, compressed_history
                    )
                    metadata["compressed_messages"] += stats["saved_messages"]
                    memory_count = self.compressor.memory_count
                    memory_block_injected = any(
                        str(message.get("content", "")).startswith("<agent_memory>")
                        for message in compressed_history
                    )
                    metadata["memory_items"] = memory_count
                    metadata["memory_injection_count"] += int(memory_block_injected)
                    print(
                        f"   保留最近 {self.compressor.keep_recent * 2} 条消息，"
                        f"本地记忆 {memory_count} 条，"
                        f"本轮{'已' if memory_block_injected else '未'}注入 <agent_memory>，"
                        f"节省 {stats['saved_messages']} 条消息"
                    )

            # 获取 AI 响应
            try:
                raw = self.client.respond(messages_to_send, temperature=self.temperature)
            except Exception as exc:
                if self.trace_writer:
                    self.trace_writer.record(
                        "llm_error",
                        {"step_number": step_num, "error": str(exc)},
                    )
                raise
            if self.trace_writer:
                self.trace_writer.record_llm_call(
                    step_number=step_num,
                    messages=messages_to_send,
                    temperature=self.temperature,
                    raw_response=raw,
                )

            # 将 AI 响应添加到历史记录
            self.conversation_history.append({"role": "assistant", "content": raw})
            try:
                parsed = self._parse_agent_response(raw)
            except ValueError as exc:
                metadata["parse_error_count"] += 1
                metadata["failure_reason"] = str(exc)
                observation = f"Agent response parse failed: {exc}"
                if self.trace_writer:
                    self.trace_writer.record_parse_error(
                        step_number=step_num,
                        raw_response=raw,
                        error=str(exc),
                    )
                step = Step(
                    thought="",
                    action="error",
                    action_input={},
                    observation=observation,
                    raw=raw,
                )
                steps.append(step)

                # 将错误观察添加到历史记录
                self.conversation_history.append(
                    {"role": "user", "content": f"观察：{observation}"}
                )

                if self.step_callback:
                    self.step_callback(step_num, step)
                if self.trace_writer:
                    self.trace_writer.record_step(step_number=step_num, step=step)
                if plan and self.planner and self.enable_adaptive_replanning:
                    plan = self._try_replan(
                        task,
                        plan,
                        observation,
                        metadata,
                        action="error",
                        step_number=step_num,
                        error_kind="parse_error",
                    )
                continue
            if self._last_parse_repaired:
                metadata["parse_repair_count"] += 1

            # 获取动作、thought 和输入
            action = parsed.get("action", "").strip()
            thought = parsed.get("thought", "").strip()
            action_input = parsed.get("action_input")

            # 检查是否完成
            if action == "finish":
                final = self._format_final_answer(action_input)
                accepted, observation, _review = self._review_completion(
                    task=task,
                    completion_text=final,
                    steps=steps,
                    metadata=metadata,
                    step_num=step_num,
                    action=action,
                )
                step = Step(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation="<finished>" if accepted else observation,
                    raw=raw,
                )
                steps.append(step)

                if accepted:
                    metadata["status"] = "success"
                    metadata["failure_reason"] = ""
                    metadata["duration_seconds"] = time.perf_counter() - started_at
                    # 添加完成标记到历史记录
                    self.conversation_history.append(
                        {"role": "user", "content": f"任务完成：{final}"}
                    )
                else:
                    self.conversation_history.append(
                        {"role": "user", "content": f"观察：{observation}"}
                    )

                if self.step_callback:
                    self.step_callback(step_num, step)
                if self.trace_writer:
                    self.trace_writer.record_step(step_number=step_num, step=step)
                if accepted:
                    return finish_result(final)
                if plan and self.planner:
                    plan = self._try_replan(
                        task,
                        plan,
                        observation,
                        metadata,
                        action=action,
                        step_number=step_num,
                        error_kind="critic_rejected",
                    )
                continue

            # 检查工具
            tool = self.tools.get(action)
            if tool is None:
                metadata["unknown_tool_count"] += 1
                metadata["failure_reason"] = f"Unknown tool: {action}"
                observation = f"Unknown tool '{action}'."
                step = Step(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation=observation,
                    raw=raw,
                )
                steps.append(step)

                # 将观察结果添加到历史记录
                self.conversation_history.append(
                    {"role": "user", "content": f"观察：{observation}"}
                )

                if self.step_callback:
                    self.step_callback(step_num, step)
                if self.trace_writer:
                    self.trace_writer.record_tool_call(
                        step_number=step_num,
                        action=action,
                        action_input=action_input,
                        observation=observation,
                        failed=True,
                    )
                    self.trace_writer.record_step(step_number=step_num, step=step)
                if plan and self.planner:
                    plan = self._try_replan(
                        task,
                        plan,
                        observation,
                        metadata,
                        action=action,
                        step_number=step_num,
                        error_kind="unknown_tool",
                    )
                continue

            error_kind = ""

            # task_complete 工具可以接受字符串或空参数
            if action == "task_complete":
                accepted = False
                if action_input is None:
                    action_input = {}
                elif isinstance(action_input, str):
                    action_input = {"message": action_input}
                elif not isinstance(action_input, dict):
                    action_input = {}
                try:
                    observation = tool.execute(action_input)
                except Exception as exc:  # noqa: BLE001 - 将工具错误传递给 LLM
                    metadata["tool_error_count"] += 1
                    metadata["failure_reason"] = str(exc)
                    observation = f"Tool execution failed: {exc}"
                    error_kind = "tool_error"
                else:
                    accepted, observation, _review = self._review_completion(
                        task=task,
                        completion_text=str(observation),
                        steps=steps,
                        metadata=metadata,
                        step_num=step_num,
                        action=action,
                    )
                    if not accepted:
                        error_kind = "critic_rejected"
            elif action_input is None:
                metadata["argument_error_count"] += 1
                metadata["failure_reason"] = "Tool arguments missing"
                observation = "Tool arguments missing: action_input is null."
                error_kind = "invalid_arguments"
            elif not isinstance(action_input, dict):
                metadata["argument_error_count"] += 1
                metadata["failure_reason"] = "Tool arguments must be a JSON object"
                observation = "Tool arguments must be a JSON object."
                error_kind = "invalid_arguments"
            else:
                try:
                    observation = tool.execute(action_input)
                except Exception as exc:  # noqa: BLE001 - 将工具错误传递给 LLM
                    metadata["tool_error_count"] += 1
                    metadata["failure_reason"] = str(exc)
                    observation = f"Tool execution failed: {exc}"
                    error_kind = "tool_error"

            step = Step(
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
                raw=raw,
            )
            steps.append(step)
            if self.trace_writer:
                self.trace_writer.record_tool_call(
                    step_number=step_num,
                    action=action,
                    action_input=action_input,
                    observation=observation,
                    failed=self._is_failure_observation(observation),
                )

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
            if self.trace_writer:
                self.trace_writer.record_step(step_number=step_num, step=step)

            if self._is_failure_observation(observation) and plan and self.planner:
                plan = self._try_replan(
                    task,
                    plan,
                    observation,
                    metadata,
                    action=action,
                    step_number=step_num,
                    error_kind=error_kind or None,
                )

            # 检查是否调用了 task_complete 工具
            if (
                action == "task_complete"
                and accepted
                and not self._is_failure_observation(observation)
            ):
                metadata["status"] = "success"
                metadata["failure_reason"] = ""
                metadata["duration_seconds"] = time.perf_counter() - started_at
                return finish_result(observation)

        metadata["status"] = "max_steps_exceeded"
        metadata["duration_seconds"] = time.perf_counter() - started_at
        metadata["failure_reason"] = metadata["failure_reason"] or "Max steps exceeded"
        return finish_result("Reached step limit without completion.")

    def _apply_skills_for_task(self, task: str) -> List[str]:
        """根据任务自动选择并激活相关技能。"""
        # 恢复基础状态，避免上一次任务的技能残留
        self.system_prompt = self._base_system_prompt
        self.tools = dict(self._base_tools)

        # 自动选择
        selected = self.skill_manager.select_skills_for_task(task)
        if not selected:
            self.skill_manager.deactivate_all()
            return []

        # 激活选中技能
        self.skill_manager.activate_skills(selected)

        # 追加技能 prompt
        prompt_addition = self.skill_manager.get_active_prompt_additions()
        if prompt_addition:
            self.system_prompt += prompt_addition

        # 合并技能工具
        skill_tools = self.skill_manager.get_active_tools()
        for tool in skill_tools:
            self.tools[tool.name] = tool

        # 打印激活信息
        display_names = []
        for name in selected:
            skill = self.skill_manager.skills.get(name)
            if skill:
                display_names.append(skill.get_metadata().display_name)
        if display_names:
            print(f"\n[skills] 已激活技能：{', '.join(display_names)}")
        return selected

    def _build_user_prompt(self, task: str, steps: List[Step], plan: List[PlanStep] = None) -> str:
        """
        构建用户提示词

        Args:
            task (str): 当前任务描述
            steps (List[Step]): 已执行的步骤列表
            plan (List[PlanStep], optional): 执行计划

        Returns:
            prompt (str): 构建好的用户提示词字符串
        """
        lines: List[str] = [f"任务：{task.strip()}"]

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
                lines.append(
                    f"步骤 {index} 输入：{json.dumps(step.action_input, ensure_ascii=False)}"
                )
                lines.append(f"步骤 {index} 观察：{step.observation}")
        lines.append(
            '\n用 JSON 对象回应：{"thought": string, "action": string, "action_input": object|string}。'
        )
        return "\n".join(lines)

    def _review_completion(
        self,
        *,
        task: str,
        completion_text: str,
        steps: List[Step],
        metadata: Dict[str, Any],
        step_num: int,
        action: str,
    ) -> tuple[bool, str, Optional[CriticReview]]:
        if self.critic is None:
            return True, completion_text, None

        try:
            review = self.critic.review(
                task=task,
                candidate_answer=completion_text,
                metadata=metadata,
                steps=[step.__dict__ for step in steps],
                failure_feedback=metadata.get("failure_reason", ""),
            )
        except Exception as exc:  # noqa: BLE001 - critic should not hide the candidate result
            metadata["critic_error"] = str(exc)
            failure_observation = f"Critic review failed: {exc}"
            if self.trace_writer:
                self.trace_writer.record_critic_review(
                    step_number=step_num,
                    review={
                        "action": action,
                        "passed": False,
                        "score": 0.0,
                        "summary": failure_observation,
                        "reasons": [str(exc)],
                        "suggested_fixes": [],
                        "error": type(exc).__name__,
                    },
                )
            return False, failure_observation, None

        metadata["critic_review_count"] += 1
        metadata["critic_last_score"] = review.score
        metadata["critic_last_passed"] = review.passed
        if review.passed:
            metadata["critic_pass_count"] += 1
        else:
            metadata["critic_fail_count"] += 1
            metadata["critic_reject_count"] += 1
            metadata["failure_reason"] = review.summary or (
                review.reasons[0] if review.reasons else "Critic rejected completion"
            )

        if self.trace_writer:
            self.trace_writer.record_critic_review(
                step_number=step_num,
                review=self._critic_review_trace_payload(review, action=action),
            )

        if review.passed:
            return True, completion_text, review
        return False, self._format_critic_observation(review, completion_text), review

    @staticmethod
    def _format_critic_observation(review: CriticReview, completion_text: str) -> str:
        details = []
        if review.summary:
            details.append(review.summary)
        if review.reasons:
            details.append("Reasons: " + "; ".join(review.reasons))
        if review.suggested_fixes:
            details.append("Fixes: " + "; ".join(review.suggested_fixes))
        details.append(f"Candidate completion: {completion_text}")
        return "Critic rejected completion.\n" + "\n".join(details)

    def _critic_review_trace_payload(self, review: CriticReview, *, action: str) -> Dict[str, Any]:
        payload = {
            "passed": review.passed,
            "score": review.score,
            "summary": review.summary,
            "reasons": list(review.reasons),
            "suggested_fixes": list(review.suggested_fixes),
            "action": action,
        }
        if self.trace_writer and getattr(self.trace_writer, "capture_llm_io", False):
            payload["raw"] = review.raw
            payload["metadata"] = review.metadata
        return payload

    def _parse_agent_response(self, raw: str) -> Dict[str, Any]:
        """
        解析智能体响应

        Args:
            raw (str): 智能体的原始响应字符串

        Returns:
            parsed (Dict[str, Any]): 解析后的JSON对象

        Raises:
            ValueError: 当响应不是有效的JSON时抛出异常
        """
        candidate = raw.strip()
        self._last_parse_repaired = False
        if not candidate:
            raise ValueError("模型返回空响应。")

        for index, snippet in enumerate(self._json_candidates(candidate)):
            strict_json = self._is_strict_json_object(snippet)
            parsed = self._load_json_object(snippet)
            if parsed is not None:
                self._last_parse_repaired = index > 0 or snippet != candidate or not strict_json
                return parsed

        raise ValueError("Response is not a valid JSON object.")

    @staticmethod
    def _json_candidates(candidate: str) -> List[str]:
        candidates = [candidate]

        fence_match = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL | re.IGNORECASE)
        if fence_match:
            candidates.append(fence_match.group(1).strip())

        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(candidate[start : end + 1])

        repaired_candidates = []
        for item in candidates:
            repaired = ReactAgent._repair_json_text(item)
            if repaired != item:
                repaired_candidates.append(repaired)

        return candidates + repaired_candidates

    @staticmethod
    def _repair_json_text(text: str) -> str:
        text = text.strip()
        text = text.replace("“", '"').replace("”", '"').replace("’", "'")
        text = re.sub(r",(\s*[}\]])", r"\1", text)
        return text

    @staticmethod
    def _load_json_object(text: str) -> Optional[Dict[str, Any]]:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                import ast

                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    @staticmethod
    def _is_strict_json_object(text: str) -> bool:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return False
        return isinstance(parsed, dict)

    @staticmethod
    def _is_failure_observation(observation: str) -> bool:
        failure_markers = [
            "Tool execution failed",
            "Unknown tool",
            "Tool arguments",
            "parse failed",
            "Critic rejected",
            "Critic review failed",
            "returncode: 1",
            "error",
            "Error",
            "Traceback",
            "失败",
            "错误",
            "不存在",
        ]
        return any(marker in observation for marker in failure_markers)

    def _try_replan(
        self,
        task: str,
        plan: List[PlanStep],
        observation: str,
        metadata: Dict[str, Any],
        *,
        action: str = "",
        step_number: Optional[int] = None,
        error_kind: Optional[str] = None,
    ) -> List[PlanStep]:
        completed_steps = [step for step in plan if step.completed]
        signal = None
        decision = None
        repeated_failure = False
        repeated_failure_payload = None
        if self.enable_adaptive_replanning:
            repeated_failure, repeated_failure_payload = self._record_failure_signature(
                observation,
                metadata,
                action=action,
                error_kind=error_kind,
                step_number=step_number,
            )
            signal = self.replan_policy.classify(
                observation,
                action=action,
                step_number=step_number,
                error_kind=error_kind,
            )
            decision = self.replan_policy.decide(
                signal,
                replan_count=int(metadata.get("replan_count", 0)),
                max_replans=self.max_replans,
                repeated_failure=repeated_failure,
                use_repeated_failure_escape=self.enable_repeated_failure_policy_experiment,
            )
            if repeated_failure and self.enable_repeated_failure_policy_experiment:
                metadata["repeated_failure_policy_applied_count"] = (
                    int(metadata.get("repeated_failure_policy_applied_count", 0)) + 1
                )
            metadata["replan_decision_count"] += 1
            metadata["replan_strategy"] = decision.strategy
            strategy_counts = metadata.setdefault("replan_strategy_counts", {})
            strategy_counts[decision.strategy] = strategy_counts.get(decision.strategy, 0) + 1
            metadata.setdefault("replan_signals", []).append(decision.to_dict())
            if self.trace_writer:
                payload = {
                    "step_number": step_number,
                    "action": action,
                    "repeated_failure": repeated_failure,
                    **decision.to_dict(),
                }
                if repeated_failure_payload:
                    payload["repeated_failure_details"] = repeated_failure_payload
                self.trace_writer.record("replan_decision", payload)
            if not decision.should_replan:
                metadata["replan_skipped_count"] += 1
                if decision.strategy == "replan_budget_exhausted":
                    metadata["replan_maxed_count"] += 1
                return plan

        try:
            new_plan = (
                self.planner.replan(
                    task,
                    completed_steps,
                    observation,
                    error_signal=signal,
                )
                if self.planner
                else []
            )
        except Exception as exc:  # noqa: BLE001
            metadata["failure_reason"] = f"Replan failed: {exc}"
            return plan

        if new_plan:
            metadata["replan_count"] += 1
            if self.trace_writer:
                self.trace_writer.record_replan(
                    reason=observation,
                    steps=new_plan,
                    strategy=decision.strategy if decision else "",
                    signal=signal.to_dict() if signal else None,
                )
            self.conversation_history.append(
                {
                    "role": "user",
                    "content": (
                        "Recovery: execution plan was regenerated after failure.\n"
                        f"Failure observation: {observation}"
                    ),
                }
            )
            return new_plan
        return plan

    def _record_failure_signature(
        self,
        observation: str,
        metadata: Dict[str, Any],
        *,
        action: str,
        error_kind: Optional[str],
        step_number: Optional[int],
    ) -> tuple[bool, Optional[Dict[str, Any]]]:
        signature = self._failure_signature(action, error_kind, observation)
        previous = str(metadata.get("last_failure_signature") or "")
        metadata["last_failure_signature"] = signature
        if not signature or signature != previous:
            return False, None

        payload = {
            "step_number": step_number,
            "action": action,
            "kind": error_kind or "unknown",
            "signature": signature,
        }
        metadata["repeated_failure_count"] = int(metadata.get("repeated_failure_count", 0)) + 1
        metadata.setdefault("repeated_failures", []).append(payload)
        return True, payload

    @staticmethod
    def _failure_signature(
        action: str,
        error_kind: Optional[str],
        observation: str,
    ) -> str:
        compact_observation = " ".join(str(observation or "").split())[:160]
        return "|".join([str(action or ""), str(error_kind or "unknown"), compact_observation])

    def reset_conversation(self) -> None:
        """重置对话历史

        清空所有对话历史记录，为新任务做准备。
        """
        self.conversation_history = []

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取对话历史

        Returns:
            conversation_history (List[Dict[str, str]]): 对话历史记录的副本
        """
        return self.conversation_history.copy()

    @staticmethod
    def _format_final_answer(action_input: Any) -> str:
        """
        格式化最终答案

        Args:
            action_input (Any): finish动作的输入参数

        Returns:
            answer (str): 格式化后的最终答案字符串
        """
        if isinstance(action_input, str):
            return action_input
        if isinstance(action_input, dict) and "answer" in action_input:
            value = action_input["answer"]
            if isinstance(value, str):
                return value
        return json.dumps(action_input, ensure_ascii=False)
