"""观察结果的判定与边界处理。

``is_failure_observation`` 从 ``ReactAgent._is_failure_observation`` 提出来，让不住在
内核里的能力（例如工具熔断）也能复用同一份失败判定，而不必反向 import ReactAgent。
``ReactAgent._is_failure_observation`` 保留为指向本函数的薄委托，公开行为不变。

``ObservationBounder`` 是内核护栏：它先于 ``after_tool_result`` 钩子链执行，
保证模型、对话历史与 trace 看到的是同一份（可能已截断的）文本。
"""

from __future__ import annotations

from typing import Any

from dm_agent.memory.context_budget import truncate_observation

from .run_state import RunContext

# 判定一条观察是否代表失败。措辞约束见 memory/context_budget 模块文档：
# 内核生成的护栏文案（截断标记、守卫拒绝、熔断拦截）都刻意避开这些词。
FAILURE_MARKERS = (
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
)


def is_failure_observation(observation: str) -> bool:
    """观察文本里是否出现失败标记。"""
    return any(marker in observation for marker in FAILURE_MARKERS)


class ObservationBounder:
    """按字符上限截断观察，并把截断事实记进 metadata 与 trace。"""

    def __init__(self, *, max_chars: int, trace_writer: Any | None = None) -> None:
        self.max_chars = max_chars
        self.trace_writer = trace_writer

    def bound(
        self,
        observation: Any,
        *,
        action: str,
        action_input: Any,
        context: RunContext,
    ) -> str:
        """截断超长观察并记录审计信息；模型、历史与 trace 看到同一份文本。"""
        result = truncate_observation(
            str(observation),
            max_chars=self.max_chars,
            action=action,
            action_input=action_input,
        )
        if result.truncated:
            metadata = context.metadata
            metadata["truncation_count"] += 1
            metadata["truncated_chars_saved"] += result.original_chars - result.kept_chars
            if self.trace_writer:
                self.trace_writer.record(
                    "observation_truncated",
                    {
                        "step_number": context.step_number,
                        "action": action,
                        "original_chars": result.original_chars,
                        "kept_chars": result.kept_chars,
                        "original_lines": result.original_lines,
                    },
                )
        return result.text
