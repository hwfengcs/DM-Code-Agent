"""通过生命周期事件实现的内置安全守卫。"""

from __future__ import annotations

from typing import Any

from dm_agent.memory.context_budget import FileLedger

from .events import AfterToolResultEvent, BeforeToolCallEvent

READ_ACTIONS = frozenset({"read_file", "search_in_file"})
WRITE_ACTIONS = frozenset({"edit_file", "create_file"})


class ReadBeforeEditGuard:
    """要求 edit_file 前已读取目标，并在每次写入后重新读取。"""

    def __init__(self, *, enabled: bool, trace_writer: Any | None = None) -> None:
        self.enabled = enabled
        self.trace_writer = trace_writer
        self._ledger = FileLedger()

    def reset(self) -> None:
        """每个 run 独立维护文件访问证据。"""
        self._ledger.reset()

    def before_tool_call(self, event: BeforeToolCallEvent) -> dict[str, Any] | None:
        """检查 edit_file，并以标准 block 结果拦截未读或已过期的编辑。"""
        if not self.enabled or event.tool_name != "edit_file":
            return None
        path = event.arguments.get("path")
        if not isinstance(path, str) or not path:
            return None
        reason = self._ledger.check_edit(path)
        if not reason:
            return None

        event.metadata["edit_guard_block_count"] = (
            int(event.metadata.get("edit_guard_block_count", 0)) + 1
        )
        if self.trace_writer:
            self.trace_writer.record(
                "edit_guard",
                {
                    "step_number": event.step_number,
                    "path": path,
                    "reason": reason,
                },
            )
        return {"block": True, "reason": _block_message(path, reason)}

    def after_tool_result(self, event: AfterToolResultEvent) -> None:
        """只登记 runner 正常返回的文件访问，保持旧守卫语义。"""
        if not event.tool_succeeded:
            return
        path = event.arguments.get("path")
        if not isinstance(path, str) or not path:
            return
        if _observation_reports_missing_path(event.observation):
            return
        if event.tool_name in READ_ACTIONS:
            self._ledger.note_read(path, event.step_number)
        elif event.tool_name in WRITE_ACTIONS:
            self._ledger.note_write(path, event.step_number)


def _block_message(path: str, reason: str) -> str:
    # 文案刻意避开失败关键词（error/失败/不存在等），拦截不应触发 replan。
    if reason == "stale_read":
        return (
            f"Edit blocked: {path} changed after your last read in this run. "
            "Re-read the target range with read_file (line_start/line_end) to get "
            "current line numbers, then edit."
        )
    return (
        f"Edit blocked: {path} has not been read in this run yet. "
        "Read the target range with read_file (line_start/line_end) first, then edit."
    )


def _observation_reports_missing_path(observation: str) -> bool:
    text = str(observation).strip()
    return (
        len(text) <= 300
        and text.startswith(("文件 ", "路径 "))
        and text.endswith(("不存在。", "不是文件。"))
    )
