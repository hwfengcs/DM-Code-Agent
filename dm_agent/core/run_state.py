"""一次 run 期间的可变状态：推理步骤、共享环境与遥测 metadata。

这些结构从 ``ReactAgent`` 里提出来，让内核之外的协作者（观察截断、工具调用、
重规划、checkpoint）不必反向 import ``ReactAgent``，也不必在每个签名里逐个
透传 ``run_id`` / ``step_number`` / ``metadata`` 三件套。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    """表示智能体的一个推理步骤。"""

    thought: str  # 智能体的思考过程
    action: str  # 要执行的动作/工具名称
    action_input: Any  # 动作的输入参数
    observation: str  # 执行动作后的观察结果
    raw: str = ""  # 原始响应内容


@dataclass
class RunContext:
    """一次 run 期间在内核与协作者之间共享的环境信息。

    生命周期钩子、观察截断、写前备份与 checkpoint 都要读同一组
    ``(run_id, step_number, metadata)``；``history_entry_ids`` 与
    ``ReactAgent.conversation_history`` 逐位对应，是「第几条消息 = 会话日志里的哪条
    entry」这个映射的唯一来源（压缩条目的 ``first_kept_entry_id`` 就取自这里）。

    **必须原地改，不要整体替换**：``LLMRequestClient`` 在构造期就绑定了
    ``as_event_context``，换成新实例会让它继续读旧对象。
    """

    run_id: str = ""
    step_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    history_entry_ids: list[str] = field(default_factory=list)

    def begin(self, *, run_id: str, metadata: dict[str, Any]) -> None:
        """进入新一轮 run，原地重置共享环境。"""
        self.run_id = run_id
        self.step_number = 0
        self.metadata = metadata
        self.history_entry_ids.clear()

    def as_event_context(self) -> tuple[str, int, dict[str, Any]]:
        """``LLMRequestClient`` 需要的上下文取值回调。"""
        return self.run_id, self.step_number, self.metadata


def initial_run_metadata(
    *,
    attempt: int,
    planning_enabled: bool,
    compression_enabled: bool,
    skills_enabled: bool,
    edit_guard_enabled: bool,
    memory_hygiene_enabled: bool,
    llm_compression_enabled: bool,
    circuit_breaker_enabled: bool,
    adaptive_replanning_enabled: bool,
    max_replans: int,
    repeated_failure_policy_experiment_enabled: bool,
) -> dict[str, Any]:
    """构造一次 run 的遥测 metadata 初值。

    键的顺序即 checkpoint JSON 与 trace 里的字段顺序，改动前请确认没有下游依赖。
    """
    return {
        "status": "running",
        "planning_enabled": planning_enabled,
        "compression_enabled": compression_enabled,
        "skills_enabled": skills_enabled,
        "activated_skills": [],
        "initial_plan_steps": 0,
        "parse_error_count": 0,
        "parse_repair_count": 0,
        "tool_error_count": 0,
        "unknown_tool_count": 0,
        "argument_error_count": 0,
        "replan_count": 0,
        "replan_budget_exhausted_count": 0,
        "compressed_messages": 0,
        "memory_compression_count": 0,
        "budget_compression_count": 0,
        "truncation_count": 0,
        "truncated_chars_saved": 0,
        "edit_guard_enabled": edit_guard_enabled,
        "edit_guard_block_count": 0,
        "memory_hygiene_enabled": memory_hygiene_enabled,
        "llm_compression_enabled": llm_compression_enabled,
        "circuit_breaker_enabled": circuit_breaker_enabled,
        "circuit_breaker_block_count": 0,
        "circuit_breaker_trip_count": 0,
        "memory_invalidation_count": 0,
        "llm_summary_count": 0,
        "llm_summary_error_count": 0,
        "memory_log_count": 0,
        "memory_items": 0,
        "memory_injection_count": 0,
        "failure_reason": "",
        "llm_retry_count": 0,
        "backup_count": 0,
        "backup_dir": "",
        "adaptive_replanning_enabled": adaptive_replanning_enabled,
        "max_replans": max_replans,
        "replan_decision_count": 0,
        "replan_skipped_count": 0,
        "replan_maxed_count": 0,
        "replan_strategy": "",
        "replan_strategy_counts": {},
        "replan_signals": [],
        "last_failure_signature": "",
        "repeated_failure_count": 0,
        "repeated_failures": [],
        "repeated_failure_policy_experiment_enabled": repeated_failure_policy_experiment_enabled,
        "repeated_failure_policy_applied_count": 0,
        "terminal_action_alias_count": 0,
        "terminal_action_aliases": [],
        # 本次尝试序号；``on_run_end`` 处理器请求重试时由 ``run()`` 递增。
        "trial": attempt,
    }
