"""由 LLM API 驱动的 ReAct 风格智能体。"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from dm_agent.clients.base_client import BaseLLMClient
from dm_agent.memory.context_compressor import ContextCompressor
from dm_agent.prompts import build_code_agent_prompt
from dm_agent.tools.base import Tool

from .capabilities import AgentCapability, CapabilityContext
from .checkpoint import RunCheckpoint
from .completion import CompletionGate, build_completion_summary, format_final_answer
from .context_window import ContextWindow
from .critic import CriticAgent
from .events import (
    AfterToolResultEvent,
    BeforeToolCallEvent,
    EventBus,
    HookFailure,
    LLMRequestClient,
    RunEndEvent,
    RunStartEvent,
)
from .guards import WRITE_ACTIONS, ReadBeforeEditGuard
from .observation import ObservationBounder, is_failure_observation
from .persistence import (
    RunPersistence,
    agent_config_snapshot,
    json_safe_metadata,
    metadata_from_checkpoint,
    plan_from_checkpoint,
    plan_to_checkpoint,
    steps_from_checkpoint,
    warn_on_config_mismatch,
)
from .planner import AdaptiveReplanPolicy, PlanStep, TaskPlanner
from .reflexion import EpisodicMemory, Reflector
from .replan import FailureContext, ReplanCoordinator
from .response_parser import normalize_action, parse_agent_response
from .run_state import RunContext, Step, initial_run_metadata

__all__ = ["ReactAgent", "Step"]


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

    # 非 adaptive 默认路径的 replan 成本护栏（max_replans>=0 时以其为准）。
    DEFAULT_REPLAN_BUDGET = 5

    def __init__(
        self,
        client: BaseLLMClient,
        tools: list[Tool],
        *,
        max_steps: int = 200,
        temperature: float = 0.0,
        system_prompt: str | None = None,
        step_callback: Callable[[int, Step], None] | None = None,  # 步骤回调函数
        enable_planning: bool = True,  # 是否启用规划
        enable_compression: bool = True,  # 是否启用上下文压缩
        skill_manager: Any | None = None,  # 技能管理器
        trace_writer: Any | None = None,
        capabilities: Sequence[AgentCapability] = (),
        enable_reflexion: bool = False,
        max_trials: int = 3,
        reflector: Reflector | None = None,
        reflexion_memory: EpisodicMemory | None = None,
        critic: CriticAgent | None = None,
        enable_adaptive_replanning: bool = False,
        replan_policy: AdaptiveReplanPolicy | None = None,
        max_replans: int = -1,
        enable_repeated_failure_policy_experiment: bool = False,
        max_observation_chars: int = 8000,
        context_token_budget: int = 24000,
        enable_edit_guard: bool = True,
        enable_memory_hygiene: bool = False,
        enable_llm_compression: bool = False,
        enable_circuit_breaker: bool = False,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_cooldown: int = 5,
        event_bus: EventBus | None = None,
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
        self.trace_writer = trace_writer
        self.event_bus = event_bus or EventBus()
        self._run_context = RunContext()
        request_client = LLMRequestClient(
            client,
            self.event_bus,
            self._run_context.as_event_context,
            self._record_hook_error,
        )

        def client_for(phase: str) -> BaseLLMClient:
            return cast(BaseLLMClient, request_client.with_phase(phase))

        self._request_client = client_for("agent")
        self._completion_gate = CompletionGate(self.event_bus, on_error=self._record_hook_error)

        self.tools = {tool.name: tool for tool in tools}
        self.tools_list = tools  # 保留工具列表用于规划器
        self.max_steps = max_steps
        self.temperature = temperature
        self.system_prompt = system_prompt or build_code_agent_prompt(tools)
        self.step_callback = step_callback
        # 多轮对话历史记录
        self.conversation_history: list[dict[str, str]] = []

        # 规划器
        self.enable_planning = enable_planning
        self.planner = TaskPlanner(client_for("planner"), tools) if enable_planning else None

        # 上下文压缩器：默认先充分利用现代 LLM 上下文，长会话再分批压缩。
        # token 预算超限时也会提前触发压缩（0 表示只按消息节奏压缩）。
        self.enable_compression = enable_compression
        self.context_token_budget = max(0, int(context_token_budget))
        self.enable_memory_hygiene = enable_memory_hygiene
        self.enable_llm_compression = enable_llm_compression
        self.compressor = (
            ContextCompressor(
                client_for("compression"),
                compress_every=20,
                keep_recent=8,
                token_budget=self.context_token_budget,
                enable_hygiene=enable_memory_hygiene,
                use_llm_summary=enable_llm_compression,
            )
            if enable_compression
            else None
        )
        self._context_window = ContextWindow(
            compressor=self.compressor,
            enabled=enable_compression,
            memory_hygiene=enable_memory_hygiene,
            llm_compression=enable_llm_compression,
            trace_writer=trace_writer,
        )
        # 单条工具观察的字符上限；0 表示不截断。
        self.max_observation_chars = max(0, int(max_observation_chars))
        self._observation_bounder = ObservationBounder(
            max_chars=self.max_observation_chars, trace_writer=trace_writer
        )
        self._persistence = RunPersistence(trace_writer=trace_writer)
        # read-before-edit 守卫：edit_file 前必须读过目标文件，且写后需重读。
        self.enable_edit_guard = enable_edit_guard
        self._edit_guard = ReadBeforeEditGuard(enabled=enable_edit_guard, trace_writer=trace_writer)
        # 工具熔断器（默认关）：同一 action+error 连续失败达到阈值后临时禁用。
        self.enable_circuit_breaker = enable_circuit_breaker
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_cooldown = circuit_breaker_cooldown

        # 技能管理器
        self.skill_manager = skill_manager
        self._base_system_prompt = self.system_prompt
        self._base_tools = dict(self.tools)
        self.enable_reflexion = enable_reflexion
        self.max_trials = max_trials
        # 经验记忆是需要随 checkpoint 存取、随 --reflexion-memory-file 落盘的状态，
        # 因此留在 Agent 上；ReflexionLoop 与它共享同一个实例。
        # 显式判 None：空 EpisodicMemory 是 falsy，`or` 会丢弃注入的实例
        # （如 --reflexion-memory-file 加载出的空记忆）。
        self.reflexion_memory = (
            reflexion_memory if reflexion_memory is not None else EpisodicMemory()
        )
        # reflector / critic 的 client 由对应能力在 install 时接到 phase 包装客户端上。
        self.reflector = reflector
        self.critic = critic
        self.enable_adaptive_replanning = enable_adaptive_replanning
        self.replan_policy = replan_policy or AdaptiveReplanPolicy()
        self.max_replans = max_replans
        self.enable_repeated_failure_policy_experiment = enable_repeated_failure_policy_experiment
        self._replan_coordinator = ReplanCoordinator(
            planner=self.planner,
            policy=self.replan_policy,
            trace_writer=trace_writer,
            adaptive=enable_adaptive_replanning,
            max_replans=max_replans,
            repeated_failure_experiment=enable_repeated_failure_policy_experiment,
        )

        # 可选能力装配：显式传入的 capabilities 之后，追加旧开关等价的内置能力。
        # 注册顺序即钩子执行顺序，能力先于内核内置守卫注册，与迁移前的判定次序一致。
        self.capabilities: list[AgentCapability] = list(capabilities)
        self.capabilities.extend(self._builtin_capabilities())
        capability_context = CapabilityContext(
            event_bus=self.event_bus,
            client_for=client_for,
            trace_writer=trace_writer,
        )
        for capability in self.capabilities:
            capability.install(capability_context)
            # ReflexionLoop 在 install 时可能补建了默认 Reflector，同步回来保持可观察。
            self.reflector = getattr(capability, "reflector", None) or self.reflector

        self.event_bus.on(
            "before_tool_call",
            self._edit_guard.before_tool_call,
            name="builtin.read_before_edit_guard",
        )
        self.event_bus.on(
            "after_tool_result",
            self._edit_guard.after_tool_result,
            name="builtin.read_before_edit_ledger",
        )

    def _builtin_capabilities(self) -> list[AgentCapability]:
        """把仍然保留的旧构造参数翻译成等价的内置能力实例。

        过渡策略：``--enable-critic`` 等 CLI 开关及其对应的构造参数语义完全不变，
        只是内部改为「安装对应的内置扩展」。
        """
        from dm_agent.extensions.capabilities import (
            CircuitBreakerGate,
            CriticGate,
            ReflexionLoop,
        )

        builtin: list[AgentCapability] = []
        if self.enable_circuit_breaker:
            builtin.append(
                CircuitBreakerGate(
                    threshold=self.circuit_breaker_threshold,
                    cooldown_steps=self.circuit_breaker_cooldown,
                )
            )
        if self.critic is not None:
            builtin.append(CriticGate(self.critic))
        if self.enable_reflexion:
            builtin.append(
                ReflexionLoop(
                    memory=self.reflexion_memory,
                    max_trials=self.max_trials,
                    reflector=self.reflector,
                )
            )
        return builtin

    def run(
        self,
        task: str,
        *,
        max_steps: int | None = None,
        checkpoint_path: Path | None = None,
        resume_state: RunCheckpoint | None = None,
    ) -> dict[str, Any]:
        """跑一次任务，并让 ``on_run_end`` 处理器决定是否重试。

        重试时对话历史恢复到调用前的快照，因此每次尝试都是干净的一轮；
        ``on_run_start`` 处理器可以借 ``prompt_suffix`` 把上一轮的经验带进来
        （内置 Reflexion 多 trial 就是这么实现的）。
        """
        if not isinstance(task, str) or not task.strip():
            raise ValueError("任务必须是非空字符串。")
        if (
            checkpoint_path is not None or resume_state is not None
        ) and self.event_bus.has_handlers("on_run_end"):
            raise ValueError("checkpoint/resume 暂不支持与 on_run_end 重试同时使用。")

        initial_history = [dict(message) for message in self.conversation_history]
        attempt = 1
        while True:
            if attempt > 1:
                self.conversation_history = [dict(message) for message in initial_history]
            result = self._run_once(
                task,
                max_steps=max_steps,
                attempt=attempt,
                checkpoint_path=checkpoint_path if attempt == 1 else None,
                resume_state=resume_state if attempt == 1 else None,
            )
            end_event = RunEndEvent(
                task=task,
                attempt=attempt,
                run_id=self._run_context.run_id,
                result=result,
                metadata=result.get("metadata", {}),
            )
            decision = self.event_bus.emit_run_end(end_event, on_error=self._record_hook_error)
            if decision is None or not decision.get("retry"):
                return result
            attempt += 1

    def _record_hook_error(self, failure: HookFailure) -> None:
        if self.trace_writer:
            self.trace_writer.record("hook_error", failure.to_trace_payload())

    def _run_once(
        self,
        task: str,
        *,
        max_steps: int | None = None,
        attempt: int = 1,
        checkpoint_path: Path | None = None,
        resume_state: RunCheckpoint | None = None,
    ) -> dict[str, Any]:
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

        # 每次尝试都从基础 prompt/工具重新出发，避免上一次 run（技能、prompt 追加）的残留。
        self.system_prompt = self._base_system_prompt
        self.tools = dict(self._base_tools)

        started_at = time.perf_counter()
        steps: list[Step] = []
        limit = max_steps or self.max_steps
        self._edit_guard.reset()
        run_token = getattr(self.trace_writer, "run_id", "") or uuid.uuid4().hex[:12]
        retry_baseline = getattr(self.client, "total_respond_retries", 0)
        self._context_window.reset()
        metadata: dict[str, Any] = initial_run_metadata(
            attempt=attempt,
            planning_enabled=self.enable_planning,
            compression_enabled=self.enable_compression,
            skills_enabled=bool(self.skill_manager),
            edit_guard_enabled=self.enable_edit_guard,
            memory_hygiene_enabled=self.enable_memory_hygiene,
            llm_compression_enabled=self.enable_llm_compression,
            circuit_breaker_enabled=self.enable_circuit_breaker,
            critic_enabled=self.critic is not None,
            adaptive_replanning_enabled=self.enable_adaptive_replanning,
            max_replans=self.max_replans,
            repeated_failure_policy_experiment_enabled=(
                self.enable_repeated_failure_policy_experiment
            ),
            reflexion_lesson_count=len(self.reflexion_memory),
        )
        self._run_context.begin(run_id=run_token, metadata=metadata)
        start_event = RunStartEvent(
            task=task,
            attempt=attempt,
            run_id=run_token,
            metadata=metadata,
        )
        prompt_suffix = self.event_bus.emit_run_start(start_event, on_error=self._record_hook_error)
        if self.trace_writer:
            self.trace_writer.start_run(
                task,
                metadata={
                    "max_steps": limit,
                    "temperature": self.temperature,
                    "planning_enabled": self.enable_planning,
                    "compression_enabled": self.enable_compression,
                    "max_observation_chars": self.max_observation_chars,
                    "context_token_budget": self.context_token_budget,
                    "edit_guard_enabled": self.enable_edit_guard,
                    "skills_enabled": bool(self.skill_manager),
                    "reflexion_enabled": metadata["reflexion_enabled"],
                    "critic_enabled": metadata["critic_enabled"],
                    "adaptive_replanning_enabled": self.enable_adaptive_replanning,
                    "max_replans": self.max_replans,
                    "repeated_failure_policy_experiment_enabled": (
                        self.enable_repeated_failure_policy_experiment
                    ),
                    "trial": metadata["trial"],
                    "max_trials": metadata["max_trials"],
                    "reflexion_lesson_count": metadata["reflexion_lesson_count"],
                    "tools": [
                        {"name": tool.name, "description": tool.description}
                        for tool in self.tools_list
                    ],
                },
            )

        def finish_result(final_answer: str) -> dict[str, Any]:
            metadata["llm_retry_count"] = (
                getattr(self.client, "total_respond_retries", 0) - retry_baseline
            )
            if metadata.get("backup_count"):
                print(f"[backup] 修改前的原文件备份目录：{metadata['backup_dir']}")
            if metadata.get("status") == "success":
                metadata["completion_summary"] = build_completion_summary(final_answer, steps)
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
        if prompt_suffix:
            self.system_prompt += "\n\n" + prompt_suffix

        # 第一步：生成计划（如果启用）；resume 时改为恢复既有状态
        plan: list[PlanStep] = []
        resume_from = 0
        if resume_state is not None:
            plan, resume_from = self._restore_from_checkpoint(resume_state, steps, metadata)
            if self.trace_writer:
                self.trace_writer.record(
                    "run_resumed",
                    {"from_step": resume_from, "history_messages": len(self.conversation_history)},
                )
            print(f"[resume] 已恢复 checkpoint，从第 {resume_from + 1} 步继续执行")
        else:
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

        for step_num in range(resume_from + 1, limit + 1):
            self._run_context.step_number = step_num
            # 每步开始前落盘上一步完成后的快照（若启用 checkpoint）。
            if checkpoint_path is not None:
                self._save_checkpoint_snapshot(
                    checkpoint_path,
                    task=task,
                    step_count=step_num - 1,
                    steps=steps,
                    metadata=metadata,
                    plan=plan,
                    limit=limit,
                )
            # 第二步：整理旧上下文为本地记忆（如果需要）
            messages_to_send = self._context_window.build_messages(
                self.system_prompt,
                self.conversation_history,
                context=self._run_context,
            )

            # 获取 AI 响应
            try:
                raw = self._request_client.respond(messages_to_send, temperature=self.temperature)
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
                parsed_response = parse_agent_response(raw)
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
                    plan = self._replan_after_failure(
                        task,
                        plan,
                        metadata,
                        FailureContext(
                            observation=observation,
                            action="error",
                            step_number=step_num,
                            error_kind="parse_error",
                        ),
                    )
                continue
            parsed = parsed_response.data
            if parsed_response.repaired:
                metadata["parse_repair_count"] += 1

            # 获取动作、thought 和输入
            raw_action_value = parsed.get("action", "")
            raw_action = "" if raw_action_value is None else str(raw_action_value).strip()
            action = normalize_action(raw_action)
            if action != raw_action:
                metadata["terminal_action_alias_count"] += 1
                metadata["terminal_action_aliases"].append(
                    {
                        "step_number": step_num,
                        "raw": raw_action,
                        "normalized": action,
                    }
                )
            thought = parsed.get("thought", "").strip()
            action_input = parsed.get("action_input")

            # 检查是否完成
            if action == "finish":
                final = format_final_answer(action_input)
                accepted, observation = self._completion_gate.review(
                    task=task,
                    action=action,
                    completion_text=final,
                    steps=steps,
                    context=self._run_context,
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
                    plan = self._replan_after_failure(
                        task,
                        plan,
                        metadata,
                        FailureContext(
                            observation=observation,
                            action=action,
                            step_number=step_num,
                            error_kind="critic_rejected",
                        ),
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
                    plan = self._replan_after_failure(
                        task,
                        plan,
                        metadata,
                        FailureContext(
                            observation=observation,
                            action=action,
                            step_number=step_num,
                            error_kind="unknown_tool",
                        ),
                    )
                continue

            error_kind = ""
            guard_blocked = False
            accepted = False
            arguments_ready = True

            # task_complete 工具可以接受字符串或空参数
            if action == "task_complete":
                if action_input is None:
                    action_input = {}
                elif isinstance(action_input, str):
                    action_input = {"message": action_input}
                elif not isinstance(action_input, dict):
                    action_input = {}
            elif action_input is None:
                metadata["argument_error_count"] += 1
                metadata["failure_reason"] = "Tool arguments missing"
                observation = "Tool arguments missing: action_input is null."
                error_kind = "invalid_arguments"
                arguments_ready = False
            elif not isinstance(action_input, dict):
                metadata["argument_error_count"] += 1
                metadata["failure_reason"] = "Tool arguments must be a JSON object"
                observation = "Tool arguments must be a JSON object."
                error_kind = "invalid_arguments"
                arguments_ready = False

            if arguments_ready:
                before_event = BeforeToolCallEvent(
                    tool_name=action,
                    arguments=cast(dict[str, Any], action_input),
                    step_number=step_num,
                    run_id=run_token,
                    metadata=metadata,
                )
                block = self.event_bus.emit_before_tool_call(
                    before_event, on_error=self._record_hook_error
                )
                action_input = before_event.arguments
                if block is not None:
                    guard_blocked = True  # 被拦下的调用不计入计划完成
                    observation = str(block["reason"])
                else:
                    if action in WRITE_ACTIONS:
                        self._persistence.backup_before_write(action_input, self._run_context)
                    tool_succeeded = False
                    try:
                        raw_observation = str(tool.execute(action_input))
                    except Exception as exc:
                        metadata["tool_error_count"] += 1
                        metadata["failure_reason"] = str(exc)
                        raw_observation = f"Tool execution failed: {exc}"
                        error_kind = "tool_error"
                    else:
                        tool_succeeded = True

                    # 观察截断是内核护栏，先于 after_tool_result 链执行：处理器看到的
                    # 就是最终写进 step、对话历史与 trace 的那份文本。
                    after_event = AfterToolResultEvent(
                        tool_name=action,
                        arguments=action_input,
                        observation=self._observation_bounder.bound(
                            raw_observation,
                            action=action,
                            action_input=action_input,
                            context=self._run_context,
                        ),
                        step_number=step_num,
                        run_id=run_token,
                        tool_succeeded=tool_succeeded,
                        metadata=metadata,
                    )
                    observation = self.event_bus.emit_after_tool_result(
                        after_event, on_error=self._record_hook_error
                    )
                    if action == "task_complete" and tool_succeeded:
                        accepted, observation = self._completion_gate.review(
                            task=task,
                            action=action,
                            completion_text=str(observation),
                            steps=steps,
                            context=self._run_context,
                        )
                        if not accepted:
                            error_kind = "critic_rejected"

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

            # 更新计划进度（如果有计划；被守卫拦下的编辑不算完成）。
            # 只有下一个待办步骤的动作匹配时才标记，消除同名动作的二义性。
            if plan and self.planner and not guard_blocked:
                next_step = self.planner.get_next_step()
                if next_step and next_step.action == action:
                    self.planner.mark_completed(next_step.step_number, observation)

            # 将工具执行结果添加到历史记录
            tool_info = f"执行工具 {action}，输入：{json.dumps(action_input, ensure_ascii=False)}\n观察：{observation}"
            self.conversation_history.append({"role": "user", "content": tool_info})

            # 调用回调函数实时输出步骤
            if self.step_callback:
                self.step_callback(step_num, step)
            if self.trace_writer:
                self.trace_writer.record_step(step_number=step_num, step=step)

            if self._is_failure_observation(observation) and plan and self.planner:
                plan = self._replan_after_failure(
                    task,
                    plan,
                    metadata,
                    FailureContext(
                        observation=observation,
                        action=action,
                        step_number=step_num,
                        error_kind=error_kind or None,
                    ),
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
        if checkpoint_path is not None:
            # 步数耗尽也落一份终态快照：换更大的 --max-steps 即可 resume 续跑。
            self._save_checkpoint_snapshot(
                checkpoint_path,
                task=task,
                step_count=limit,
                steps=steps,
                metadata=metadata,
                plan=plan,
                limit=limit,
            )
        return finish_result("Reached step limit without completion.")

    def _apply_skills_for_task(self, task: str) -> list[str]:
        """根据任务自动选择并激活相关技能。"""
        # 调用点（_run_once）已用 `if self.skill_manager:` 守卫，此处的 None 分支不可达；
        # 取局部变量是为了让类型检查器完成收窄，同时避免管理器缺失时抛 AttributeError。
        manager = self.skill_manager
        if manager is None:
            return []

        # 恢复基础状态，避免上一次任务的技能残留
        self.system_prompt = self._base_system_prompt
        self.tools = dict(self._base_tools)

        # 自动选择
        selected = manager.select_skills_for_task(task)
        if not selected:
            manager.deactivate_all()
            return []

        # 激活选中技能
        manager.activate_skills(selected)

        # 追加技能 prompt
        prompt_addition = manager.get_active_prompt_additions()
        if prompt_addition:
            self.system_prompt += prompt_addition

        # 合并技能工具
        skill_tools = manager.get_active_tools()
        for tool in skill_tools:
            self.tools[tool.name] = tool

        # 打印激活信息
        display_names = []
        for name in selected:
            skill = manager.skills.get(name)
            if skill:
                display_names.append(skill.get_metadata().display_name)
        if display_names:
            print(f"\n[skills] 已激活技能：{', '.join(display_names)}")
        return selected

    def _build_user_prompt(
        self, task: str, steps: list[Step], plan: list[PlanStep] | None = None
    ) -> str:
        """
        构建用户提示词

        Args:
            task (str): 当前任务描述
            steps (List[Step]): 已执行的步骤列表
            plan (List[PlanStep], optional): 执行计划

        Returns:
            prompt (str): 构建好的用户提示词字符串
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
                lines.append(
                    f"步骤 {index} 输入：{json.dumps(step.action_input, ensure_ascii=False)}"
                )
                lines.append(f"步骤 {index} 观察：{step.observation}")
        lines.append(
            '\n用 JSON 对象回应：{"thought": string, "action": string, "action_input": object|string}。'
        )
        return "\n".join(lines)

    def _config_snapshot(self, *, max_steps: int | None = None) -> dict[str, Any]:
        """当前生效的配置快照：既用于落盘，也用于 resume 时的一致性比对。"""
        return agent_config_snapshot(
            temperature=self.temperature,
            model=getattr(self.client, "model", ""),
            enable_planning=self.enable_planning,
            enable_compression=self.enable_compression,
            enable_edit_guard=self.enable_edit_guard,
            max_observation_chars=self.max_observation_chars,
            context_token_budget=self.context_token_budget,
            max_steps=max_steps,
        )

    def _restore_from_checkpoint(
        self,
        resume_state: RunCheckpoint,
        steps: list[Step],
        metadata: dict[str, Any],
    ) -> tuple[list[PlanStep], int]:
        """从 checkpoint 恢复对话/步骤/计划/记忆，返回 (plan, 已消耗步数)。"""
        resume_from = max(0, int(resume_state.step_count))
        self.conversation_history = [dict(message) for message in resume_state.conversation_history]
        steps.extend(steps_from_checkpoint(resume_state.steps))
        metadata.update(metadata_from_checkpoint(resume_state.metadata, resume_from=resume_from))

        plan = plan_from_checkpoint(resume_state.plan)
        if plan and self.planner:
            self.planner.current_plan = plan
        if resume_state.compressor_state and self.compressor:
            self.compressor.restore_state(resume_state.compressor_state)
        if resume_state.reflexion_memory:
            self.reflexion_memory = EpisodicMemory.from_dict(resume_state.reflexion_memory)
        warn_on_config_mismatch(resume_state.agent_config, self._config_snapshot())
        return plan, resume_from

    def _save_checkpoint_snapshot(
        self,
        path: Path,
        *,
        task: str,
        step_count: int,
        steps: list[Step],
        metadata: dict[str, Any],
        plan: list[PlanStep],
        limit: int,
    ) -> None:
        """把当前 run 的可恢复状态组装成快照并落盘。"""
        checkpoint = RunCheckpoint(
            task=task,
            step_count=step_count,
            conversation_history=[dict(message) for message in self.conversation_history],
            steps=[dict(step.__dict__) for step in steps],
            metadata=json_safe_metadata(metadata),
            plan=plan_to_checkpoint(plan),
            compressor_state=self.compressor.export_state() if self.compressor else None,
            reflexion_memory=(
                self.reflexion_memory.to_dict() if len(self.reflexion_memory) else None
            ),
            agent_config=self._config_snapshot(max_steps=limit),
            cwd=str(Path.cwd()),
        )
        self._persistence.save(path, checkpoint)

    @staticmethod
    def _is_failure_observation(observation: str) -> bool:
        """委托到 ``core.observation``，让内核外的能力复用同一份失败判定。"""
        return is_failure_observation(observation)

    def _replan_after_failure(
        self,
        task: str,
        plan: list[PlanStep],
        metadata: dict[str, Any],
        failure: FailureContext,
    ) -> list[PlanStep]:
        """失败后尝试重规划；新计划生效时把恢复提示追加进对话历史。"""
        outcome = self._replan_coordinator.try_replan(
            task,
            plan,
            failure,
            metadata,
            default_budget=self.DEFAULT_REPLAN_BUDGET,
        )
        if outcome.history_note:
            self.conversation_history.append({"role": "user", "content": outcome.history_note})
        return outcome.plan

    def reset_conversation(self) -> None:
        """重置对话历史

        清空所有对话历史记录，为新任务做准备。
        """
        self.conversation_history = []
        if self.compressor:
            self.compressor.reset()

    def get_context_stats(self) -> dict[str, Any]:
        """Return current in-memory conversation and context-memory state."""
        return {
            "conversation_messages": len(self.conversation_history),
            "compression_enabled": self.enable_compression,
            "memory_items": self.compressor.memory_count if self.compressor else 0,
        }

    def get_conversation_history(self) -> list[dict[str, str]]:
        """获取对话历史

        Returns:
            conversation_history (List[Dict[str, str]]): 对话历史记录的副本
        """
        return self.conversation_history.copy()
