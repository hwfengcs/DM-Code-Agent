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
from dm_agent.tracing.writer import SessionWriter

from .capabilities import AgentCapability, CapabilityContext
from .checkpoint import RunCheckpoint
from .completion import CompletionGate, build_run_result, format_final_answer
from .context_window import ContextWindow
from .critic import CriticAgent
from .events import (
    EventBus,
    HookFailure,
    LLMRequestClient,
    RunEndEvent,
    RunStartEvent,
)
from .guards import ReadBeforeEditGuard
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
from .prompting import activate_skills, build_user_prompt
from .reflexion import EpisodicMemory, Reflector
from .replan import FailureContext, ReplanCoordinator
from .response_parser import normalize_action, parse_agent_response
from .run_state import RunContext, Step, initial_run_metadata
from .tool_invoker import ToolInvoker

__all__ = ["ReactAgent", "Step"]


class ReactAgent:
    """ReAct（推理 + 行动）循环的内核。

    职责只剩三件：装配协作者、跑主循环、维护对话历史。其余能力各自住在
    独立模块里，本类通过它们完成一步的各个环节：

    - ``core.context_window``：构造发给 LLM 的消息（按需压缩旧上下文）
    - ``core.response_parser``：容错解析模型响应
    - ``core.tool_invoker``：工具调用链（校验 → 钩子 → 备份 → 执行 → 截断）
    - ``core.completion``：完成判定与结果格式化
    - ``core.replan``：失败后的重规划与失败签名
    - ``core.persistence``：checkpoint 存取与写前备份

    可选能力（Critic、熔断、Reflexion）不住在这里，而是通过 ``core.events``
    的生命周期钩子接入，见 ``core.capabilities``。
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
        """初始化 ReactAgent。

        ``tools`` 之外的参数都有可用的默认值。带 ``enable_`` 前缀的行为类开关默认
        关闭，基础设施护栏（观察截断、token 预算、read-before-edit 守卫）默认开启；
        取值口径与 ``dm-agent`` CLI 的同名参数一致。

        Raises:
            ValueError: 工具列表为空，或 ``max_trials`` 小于 1
        """
        if not tools:
            raise ValueError("必须为 ReactAgent 提供至少一个工具。")
        if max_trials < 1:
            raise ValueError("max_trials must be at least 1.")
        self.client = client
        self.trace_writer = (
            trace_writer if isinstance(trace_writer, SessionWriter) else SessionWriter(trace_writer)
        )
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
            trace_writer=self.trace_writer,
        )
        # 单条工具观察的字符上限；0 表示不截断。
        self.max_observation_chars = max(0, int(max_observation_chars))
        self._observation_bounder = ObservationBounder(
            max_chars=self.max_observation_chars, trace_writer=self.trace_writer
        )
        self._persistence = RunPersistence(trace_writer=self.trace_writer)
        self._tool_invoker = ToolInvoker(
            event_bus=self.event_bus,
            bounder=self._observation_bounder,
            persistence=self._persistence,
            on_error=self._record_hook_error,
        )
        # read-before-edit 守卫：edit_file 前必须读过目标文件，且写后需重读。
        self.enable_edit_guard = enable_edit_guard
        self._edit_guard = ReadBeforeEditGuard(
            enabled=enable_edit_guard, trace_writer=self.trace_writer
        )
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
            trace_writer=self.trace_writer,
            adaptive=enable_adaptive_replanning,
            max_replans=max_replans,
            repeated_failure_experiment=enable_repeated_failure_policy_experiment,
        )

        # 可选能力装配：显式传入的 capabilities 之后，追加旧开关等价的内置能力。
        # 注册顺序即钩子执行顺序，能力先于内核内置守卫注册，与迁移前的判定次序一致。
        # 延迟导入：extensions 会反向 import core，模块级导入会与 core.agent 相互缠绕。
        from dm_agent.extensions.capabilities import builtin_capabilities_for

        self.capabilities: list[AgentCapability] = list(capabilities)
        self.capabilities.extend(
            builtin_capabilities_for(
                enable_circuit_breaker=enable_circuit_breaker,
                circuit_breaker_threshold=circuit_breaker_threshold,
                circuit_breaker_cooldown=circuit_breaker_cooldown,
                critic=critic,
                enable_reflexion=enable_reflexion,
                reflexion_memory=self.reflexion_memory,
                max_trials=max_trials,
                reflector=self.reflector,
            )
        )
        capability_context = CapabilityContext(
            event_bus=self.event_bus,
            client_for=client_for,
            trace_writer=self.trace_writer,
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

    def _append_history(self, role: str, content: str, *, kind: str) -> None:
        """把一条消息追加进对话历史，同时在会话日志里落一条 ``message`` 条目。

        ``conversation_history`` 与 ``RunContext.history_entry_ids`` 必须逐位对应——
        压缩条目的 ``first_kept_entry_id`` 靠这个映射把「第几条消息」翻译成 entry id。
        没有 trace_writer 时补一个空 id 占位，保证下标始终对齐。
        """
        self.conversation_history.append({"role": role, "content": content})
        entry_id = ""
        if self.trace_writer:
            entry_id = self.trace_writer.record_message(
                role=role,
                content=content,
                step_number=self._run_context.step_number,
                kind=kind,
            )
        self._run_context.history_entry_ids.append(entry_id)

    def _adopt_existing_history(self, *, kind: str) -> None:
        """让会话日志补齐「这一轮开始前就在历史里」的消息。

        ``conversation_history`` 可能在 ``_run_once`` 之前就非空（交互式多轮、
        reflexion 重试恢复的快照、resume 恢复的历史）。会话日志要能独立复现上下文，
        所以把这些消息补记成 ``message`` 条目，顺带把 ``history_entry_ids``
        对齐回 ``len(conversation_history)``。历史为空时这是个空操作。
        """
        pending = self.conversation_history[len(self._run_context.history_entry_ids) :]
        for message in pending:
            entry_id = ""
            if self.trace_writer:
                entry_id = self.trace_writer.record_message(
                    role=str(message.get("role", "")),
                    content=str(message.get("content", "")),
                    step_number=self._run_context.step_number,
                    kind=kind,
                )
            self._run_context.history_entry_ids.append(entry_id)

    def _note_observation(self, observation: str) -> None:
        """把一条观察作为 user 消息投递回对话历史。"""
        self._append_history("user", f"观察：{observation}", kind="observation")

    def _publish_step(self, step: Step, step_num: int) -> None:
        """一步收尾：实时回调 + trace 落步。"""
        if self.step_callback:
            self.step_callback(step_num, step)
        if self.trace_writer:
            self.trace_writer.record_step(step_number=step_num, step=step)

    def _run_once(
        self,
        task: str,
        *,
        max_steps: int | None = None,
        attempt: int = 1,
        checkpoint_path: Path | None = None,
        resume_state: RunCheckpoint | None = None,
    ) -> dict[str, Any]:
        """跑完整的一轮 ReAct 循环：规划 → 推理 → 行动 → 观察，直到完成或步数耗尽。

        ``run`` 负责多次尝试之间的编排，本方法只管一次尝试。

        Returns:
            含 ``final_answer`` / ``steps`` / ``metadata`` 三个键的结果字典

        Raises:
            ValueError: 任务不是非空字符串
        """
        if not isinstance(task, str) or not task.strip():
            raise ValueError("任务必须是非空字符串。")

        # 每次尝试都从基础 prompt/工具重新出发，避免上一次 run（技能、prompt 追加）的残留。
        self.system_prompt = self._base_system_prompt
        self.tools = dict(self._base_tools)

        started_at = time.perf_counter()
        steps: list[Step] = []
        limit = max_steps or self.max_steps
        if checkpoint_path is not None:
            self._persistence.prepare_session_checkpoint(checkpoint_path)
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

        # resume 必须先恢复持久化状态，再落 trace 的 run_start；否则会记录恢复前的
        # reflexion lesson 数，而最终 metadata / run_end 使用恢复后的值。
        plan: list[PlanStep] = []
        resume_from = 0
        if resume_state is not None:
            plan, resume_from = self._restore_from_checkpoint(resume_state, steps, metadata)
            metadata["reflexion_lesson_count"] = len(self.reflexion_memory)

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
            result = build_run_result(final_answer, steps, metadata)
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
        if resume_state is not None:
            self._adopt_existing_history(kind="resumed")
            if self.trace_writer:
                self.trace_writer.record(
                    "run_resumed",
                    {"from_step": resume_from, "history_messages": len(self.conversation_history)},
                )
            print(f"[resume] 已恢复 checkpoint，从第 {resume_from + 1} 步继续执行")
        else:
            self._adopt_existing_history(kind="carried")
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
            task_prompt: str = build_user_prompt(task, plan)
            self._append_history("user", task_prompt, kind="task")

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
            self._append_history("assistant", raw, kind="model_response")
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
                self._note_observation(observation)
                self._publish_step(step, step_num)
                if plan and self.planner:
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
                    self._append_history("user", f"任务完成：{final}", kind="completion")
                else:
                    self._note_observation(observation)

                self._publish_step(step, step_num)
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
                self._note_observation(observation)

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

            invocation = self._tool_invoker.invoke(
                tool,
                action=action,
                action_input=action_input,
                context=self._run_context,
            )
            action_input = invocation.arguments
            observation = invocation.observation
            error_kind = invocation.error_kind
            guard_blocked = invocation.blocked  # 被守卫拦下的编辑不算计划完成
            accepted = False
            if action == "task_complete" and invocation.tool_succeeded:
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
            self._append_history("user", tool_info, kind="tool_result")

            # 调用回调函数实时输出步骤
            self._publish_step(step, step_num)

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
        """根据任务自动选择技能，并把增量合并进本轮的 prompt 与工具表。"""
        # 调用点（_run_once）已用 `if self.skill_manager:` 守卫，此处的 None 分支不可达；
        # 取局部变量是为了让类型检查器完成收窄，同时避免管理器缺失时抛 AttributeError。
        manager = self.skill_manager
        if manager is None:
            return []

        # 恢复基础状态，避免上一次任务的技能残留
        self.system_prompt = self._base_system_prompt
        self.tools = dict(self._base_tools)

        activation = activate_skills(manager, task)
        if activation.prompt_addition:
            self.system_prompt += activation.prompt_addition
        for tool in activation.tools:
            self.tools[tool.name] = tool
        return activation.selected

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
            self._append_history("user", outcome.history_note, kind="replan_note")
        return outcome.plan

    def reset_conversation(self) -> None:
        """重置对话历史

        清空所有对话历史记录，为新任务做准备。
        """
        self.conversation_history = []
        self._run_context.history_entry_ids.clear()
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
