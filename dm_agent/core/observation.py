"""观察结果的判定与边界处理。

``is_failure_observation`` 从 ``ReactAgent._is_failure_observation`` 提出来，让不住在
内核里的能力（例如工具熔断）也能复用同一份失败判定，而不必反向 import ReactAgent。
``ReactAgent._is_failure_observation`` 保留为指向本函数的薄委托，公开行为不变。

``ObservationBounder`` 是内核护栏：它先于 ``after_tool_result`` 钩子链执行，
保证模型、对话历史与 trace 看到的是同一份（可能已截断的）文本。

判定分层的由来：观察里混着两种东西——工具**自述**的状态（"文件 X 不存在。"）和工具
**搬运**的外部内容（文件正文、子进程 stdout）。早期实现对两者一视同仁地全文扫描
``FAILURE_MARKERS``，于是读到一行 ``from errors import NotFound`` 就把一次成功的
read_file 判成失败，白烧一次重规划。``is_failure_observation`` 因此改为按来源分层，
只在工具自述的位置上判定；搬运来的正文不再参与。
"""

from __future__ import annotations

from typing import Any

from dm_agent.memory.context_budget import truncate_observation
from dm_agent.observations import FAILURE_MARKERS as FAILURE_MARKERS
from dm_agent.observations import is_failure_observation as is_failure_observation

from .run_state import RunContext


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
