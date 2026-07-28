"""完成判定与结果格式化。

内核在两处判定"任务完成"：模型直接返回 ``finish``，以及模型调用 ``task_complete``
工具。两条路径都要先把候选文本交给 ``before_finish`` 钩子链（Critic 门就挂在这里），
放行后再统一格式化成给用户看的最终答案与完成摘要。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from .events import BeforeFinishEvent, EventBus, HookErrorHandler
from .run_state import RunContext, Step

# 过于简短、无法独立说明"做了什么"的答案；命中后要另行补一段完成摘要。
TERSE_COMPLETION_ANSWERS: frozenset[str] = frozenset(
    {
        "done",
        "ok",
        "complete",
        "completed",
        "finished",
        "success",
        "fixed",
        "recovered",
        "repaired",
        "完成",
        "已完成",
        "成功",
        "修复完成",
    }
)

# 短于这个长度的答案一律视为"没说清楚"，需要补摘要。
MIN_SUMMARY_CHARS = 12
# 完成摘要里最多点名几个工具。
MAX_SUMMARY_ACTIONS = 5


class CompletionGate:
    """把完成候选交给 ``before_finish`` 链，决定放行还是打回。"""

    def __init__(self, event_bus: EventBus, *, on_error: HookErrorHandler | None = None) -> None:
        self.event_bus = event_bus
        self.on_error = on_error

    def review(
        self,
        *,
        task: str,
        action: str,
        completion_text: str,
        steps: Sequence[Step],
        context: RunContext,
    ) -> tuple[bool, str]:
        """返回 (是否放行, observation)。被打回时 observation 是拒绝理由。"""
        event = BeforeFinishEvent(
            task=task,
            action=action,
            completion_text=completion_text,
            steps=[step.__dict__ for step in steps],
            step_number=context.step_number,
            run_id=context.run_id,
            metadata=context.metadata,
        )
        block = self.event_bus.emit_before_finish(event, on_error=self.on_error)
        if block is None:
            return True, completion_text
        return False, str(block["reason"])


def build_run_result(
    final_answer: str, steps: Sequence[Step], metadata: dict[str, Any]
) -> dict[str, Any]:
    """组装一次 run 的返回值；成功时顺带补一段完成摘要。"""
    if metadata.get("status") == "success":
        metadata["completion_summary"] = build_completion_summary(final_answer, steps)
    return {
        "final_answer": final_answer,
        "steps": [step.__dict__ for step in steps],
        "metadata": metadata,
    }


def format_final_answer(action_input: Any) -> str:
    """把 ``finish`` 动作的入参格式化成最终答案文本。"""
    if isinstance(action_input, str):
        return action_input
    if isinstance(action_input, dict):
        for key in ("answer", "message", "final_answer", "summary", "result"):
            value = action_input.get(key)
            if isinstance(value, str):
                return value
    return json.dumps(action_input, ensure_ascii=False)


def build_completion_summary(final_answer: str, steps: Sequence[Step]) -> str:
    """答案本身说不清楚时，按本轮用过的工具补一段完成摘要。"""
    answer = str(final_answer or "").strip()
    if looks_like_completion_summary(answer):
        return answer
    if answer:
        return f"任务已完成。结果：{answer}"

    tool_actions: list[str] = []
    for step in steps:
        action = str(step.action or "")
        if action in {"finish", "task_complete", "error"}:
            continue
        if action not in tool_actions:
            tool_actions.append(action)
    if tool_actions:
        actions = ", ".join(tool_actions[:MAX_SUMMARY_ACTIONS])
        suffix = " 等步骤" if len(tool_actions) > MAX_SUMMARY_ACTIONS else ""
        return f"任务已完成。本轮通过 {actions}{suffix} 完成处理。"
    return "任务已完成。本轮对话已收尾。"


def looks_like_completion_summary(text: str) -> bool:
    """判断一段文本是否已经能当作完成摘要用。"""
    compact = " ".join(str(text or "").split())
    if not compact:
        return False
    if compact.lower() in TERSE_COMPLETION_ANSWERS:
        return False
    return len(compact) >= MIN_SUMMARY_CHARS
