"""工具熔断：以 ``before_tool_call`` + ``after_tool_result`` 实现的内置扩展。

迁移前这段逻辑分散在 ``ReactAgent._run_once`` 的两处内联分支里（执行前 intercept、
截断后 record），由 ``--enable-circuit-breaker`` 通过三个构造参数打开。现在它只是
一对注册在事件总线上的处理器。

两条必须保住的次序约定：

1. 熔断拦截注册在内核 read-before-edit 守卫**之前**，与迁移前「熔断先判、守卫后判」
   一致（能力统一先于内核守卫安装）。
2. 记账看到的是**截断之后**的 observation。为此内核把观察截断移到了
   ``after_tool_result`` 事件之前——截断是内核护栏，处理器看到的就是最终会写进
   对话历史与 trace 的那份文本。
"""

from __future__ import annotations

from typing import Any

from dm_agent.core.capabilities import CapabilityContext
from dm_agent.core.circuit_breaker import STATE_OPEN, ToolCircuitBreaker
from dm_agent.core.events import AfterToolResultEvent, BeforeToolCallEvent
from dm_agent.core.observation import is_failure_observation

# task_complete 是完成信号而非普通工具，始终不参与熔断。
_EXEMPT_TOOLS = frozenset({"task_complete"})


class CircuitBreakerGate:
    """同一工具同类错误连续失败达到阈值后临时拦截该工具。"""

    def __init__(self, *, threshold: int = 3, cooldown_steps: int = 5) -> None:
        self.breaker = ToolCircuitBreaker(threshold=threshold, cooldown_steps=cooldown_steps)
        self.trace_writer: Any | None = None

    def install(self, context: CapabilityContext) -> None:
        self.trace_writer = context.trace_writer
        context.event_bus.on(
            "before_tool_call",
            self.before_tool_call,
            name="builtin.circuit_breaker_intercept",
        )
        context.event_bus.on(
            "after_tool_result",
            self.after_tool_result,
            name="builtin.circuit_breaker_ledger",
        )

    def before_tool_call(self, event: BeforeToolCallEvent) -> dict[str, Any] | None:
        if event.tool_name in _EXEMPT_TOOLS:
            return None
        message = self.breaker.intercept(event.tool_name, event.step_number)
        if message is None:
            return None
        event.metadata["circuit_breaker_block_count"] = (
            int(event.metadata.get("circuit_breaker_block_count", 0)) + 1
        )
        if self.trace_writer:
            self.trace_writer.record(
                "circuit_breaker",
                {
                    "step_number": event.step_number,
                    "action": event.tool_name,
                    "phase": "blocked",
                },
            )
        return {"block": True, "reason": message}

    def after_tool_result(self, event: AfterToolResultEvent) -> None:
        if event.tool_name in _EXEMPT_TOOLS:
            return
        # runner 抛异常时内核把 observation 写成 "Tool execution failed: ..."，
        # 对应迁移前的 error_kind="tool_error"；正常返回时为空错误类别。
        error_kind = "" if event.tool_succeeded else "tool_error"
        state = self.breaker.record(
            event.tool_name,
            error_kind,
            failed=is_failure_observation(event.observation),
            step=event.step_number,
        )
        event.metadata["circuit_breaker_trip_count"] = self.breaker.total_trips
        if state == STATE_OPEN and self.trace_writer:
            self.trace_writer.record(
                "circuit_breaker",
                {
                    "step_number": event.step_number,
                    "action": event.tool_name,
                    "phase": "opened",
                },
            )
