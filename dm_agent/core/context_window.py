"""构造发给 LLM 的消息窗口：按需折叠旧上下文，并汇报折叠效果。

折叠决策在 ``memory/context_compressor.py``（本地确定性的 Mem0 风格原子记忆）。
本模块负责内核这一侧的编排：什么时候触发、折叠后往 metadata 与会话日志里记什么、
以及把"已整理上下文"的播报节流到不刷屏。

**折叠是非破坏式的**：原始消息条目一条不删，只往会话日志追加一条 ``compaction``
条目（记下折叠了哪些 entry、从哪条起保留、摘要是什么），构造消息时按这条条目
跳过被折叠的区间。于是事后可以在同一份会话日志上开关压缩重算上下文
（``tracing.session.rebuild_context``），精确量化折叠掉了什么。
"""

from __future__ import annotations

from typing import Any

from dm_agent.memory.context_budget import estimate_messages_tokens
from dm_agent.memory.context_compressor import Compaction, ContextCompressor, apply_compaction

from .run_state import RunContext

# 记忆状态播报的节流参数：首次必报，此后按间隔或明显增量才报。
MEMORY_STATUS_LOG_INTERVAL = 5
MEMORY_STATUS_SAVED_DELTA = 8
MEMORY_STATUS_ITEM_DELTA = 5

MEMORY_BLOCK_PREFIX = "<agent_memory>"


def should_log_memory_status(
    *,
    compression_count: int,
    saved_messages: int,
    memory_items: int,
    last_logged_saved_messages: int,
    last_logged_memory_items: int,
) -> bool:
    """只在记忆状态有意义地变化时才播报。"""
    if compression_count <= 1:
        return True
    if compression_count % MEMORY_STATUS_LOG_INTERVAL == 0:
        return True
    if saved_messages - last_logged_saved_messages >= MEMORY_STATUS_SAVED_DELTA:
        return True
    return memory_items - last_logged_memory_items >= MEMORY_STATUS_ITEM_DELTA


class ContextWindow:
    """把对话历史整理成一次 LLM 请求的消息列表。"""

    def __init__(
        self,
        *,
        compressor: ContextCompressor | None,
        enabled: bool,
        memory_hygiene: bool,
        llm_compression: bool,
        trace_writer: Any | None = None,
    ) -> None:
        self.compressor = compressor
        self.enabled = enabled
        self.memory_hygiene = memory_hygiene
        self.llm_compression = llm_compression
        self.trace_writer = trace_writer
        self._last_logged_memory_items = 0
        self._last_logged_saved_messages = 0

    def reset(self) -> None:
        """每个 run 重新开始节流计数。"""
        self._last_logged_memory_items = 0
        self._last_logged_saved_messages = 0

    def build_messages(
        self,
        system_prompt: str,
        history: list[dict[str, str]],
        *,
        context: RunContext,
    ) -> list[dict[str, str]]:
        """返回本步要发给 LLM 的消息；必要时先把旧上下文折叠成本地记忆。

        折叠只影响**这一次请求的消息列表**：``history`` 与会话日志里的原始条目
        都原样保留，折叠事实作为一条 ``compaction`` 条目单独落盘。
        """
        messages = [{"role": "system", "content": system_prompt}, *history]
        compressor = self.compressor
        if not (self.enabled and compressor and compressor.should_compress(history)):
            return messages

        trigger = compressor.last_trigger
        trigger_tokens = compressor.last_estimated_tokens
        compaction = compressor.plan_compaction(history)
        compressed_history = apply_compaction(history, compaction)
        messages = [{"role": "system", "content": system_prompt}, *compressed_history]

        self._record_compaction_entry(
            compaction,
            history=history,
            compressed_history=compressed_history,
            context=context,
        )
        self._record_budget_events(
            compressed_history,
            context=context,
            trigger=trigger,
            trigger_tokens=trigger_tokens,
        )
        self._record_compression_stats(history, compressed_history, context=context)
        return messages

    def _record_compaction_entry(
        self,
        compaction: Compaction,
        *,
        history: list[dict[str, str]],
        compressed_history: list[dict[str, str]],
        context: RunContext,
    ) -> None:
        """把这次折叠写成一条会话条目，让上下文事后可复算。

        ``first_kept_entry_id`` / ``folded_entry_ids`` 由会话写入门面按历史下标分别
        翻译成各 sink 的本地 id。没有会话日志（未开 --trace/--checkpoint）时什么都不做。
        """
        if not self.trace_writer:
            return
        self.trace_writer.record_compaction(
            {
                "step_number": context.step_number,
                "trigger": compaction.trigger,
                "folded_message_count": len(compaction.folded_indexes),
                "kept_message_count": len(compressed_history),
                "original_message_count": len(history),
                "summary": compaction.summary,
                "memory_items": compaction.memory_items,
                "estimated_tokens_before": compaction.estimated_tokens,
                "estimated_tokens_after": estimate_messages_tokens(compressed_history),
            },
            first_kept_index=compaction.first_kept_index,
            folded_indexes=compaction.folded_indexes,
        )

    def _record_budget_events(
        self,
        compressed_history: list[dict[str, str]],
        *,
        context: RunContext,
        trigger: str,
        trigger_tokens: int,
    ) -> None:
        """记录 token 预算相关的两类事件：被预算逼着压缩、压缩后仍然超预算。"""
        compressor = self.compressor
        if compressor is None:
            return
        if trigger == "token_budget":
            context.metadata["budget_compression_count"] += 1
            if self.trace_writer:
                self.trace_writer.record(
                    "context_budget",
                    {
                        "step_number": context.step_number,
                        "phase": "forced_compress",
                        "estimated_tokens": trigger_tokens,
                        "budget": compressor.token_budget,
                    },
                )
        if self.trace_writer and 0 < compressor.token_budget < estimate_messages_tokens(
            compressed_history
        ):
            self.trace_writer.record(
                "context_budget",
                {
                    "step_number": context.step_number,
                    "phase": "post_compress_still_over",
                    "estimated_tokens": estimate_messages_tokens(compressed_history),
                    "budget": compressor.token_budget,
                },
            )

    def _record_compression_stats(
        self,
        history: list[dict[str, str]],
        compressed_history: list[dict[str, str]],
        *,
        context: RunContext,
    ) -> None:
        """把本次压缩的效果写进 metadata，必要时播报一次。"""
        compressor = self.compressor
        if compressor is None:
            return
        metadata = context.metadata
        stats = compressor.get_compression_stats(history, compressed_history)
        metadata["compressed_messages"] += stats["saved_messages"]
        memory_count = compressor.memory_count
        memory_block_injected = any(
            str(message.get("content", "")).startswith(MEMORY_BLOCK_PREFIX)
            for message in compressed_history
        )
        metadata["memory_items"] = memory_count
        metadata["memory_injection_count"] += int(memory_block_injected)
        metadata["memory_compression_count"] += 1

        if self.memory_hygiene:
            superseded_total = compressor.memory.superseded_count
            superseded_delta = superseded_total - int(metadata["memory_invalidation_count"])
            metadata["memory_invalidation_count"] = superseded_total
            if superseded_delta > 0 and self.trace_writer:
                self.trace_writer.record(
                    "memory_invalidation",
                    {
                        "step_number": context.step_number,
                        "superseded": superseded_delta,
                        "total": superseded_total,
                    },
                )
        if self.llm_compression:
            metadata["llm_summary_count"] = compressor.llm_summary_count
            metadata["llm_summary_error_count"] = compressor.llm_summary_error_count

        if should_log_memory_status(
            compression_count=int(metadata["memory_compression_count"]),
            saved_messages=int(stats["saved_messages"]),
            memory_items=memory_count,
            last_logged_saved_messages=self._last_logged_saved_messages,
            last_logged_memory_items=self._last_logged_memory_items,
        ):
            metadata["memory_log_count"] += 1
            self._last_logged_memory_items = memory_count
            self._last_logged_saved_messages = int(stats["saved_messages"])
            print("\n[memory] 已整理旧上下文并召回相关记忆")
            print(
                f"   保留最近 {compressor.keep_recent * 2} 条消息，"
                f"本地记忆 {memory_count} 条，"
                f"本轮{'已' if memory_block_injected else '未'}注入 <agent_memory>，"
                f"节省 {stats['saved_messages']} 条消息"
            )
