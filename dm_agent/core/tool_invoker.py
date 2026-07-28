"""一次工具调用的完整链路：入参校验 -> 前置钩子 -> 写前备份 -> 执行 -> 截断 -> 后置钩子。

内核护栏（观察截断、写前备份）与扩展钩子（``before_tool_call`` /
``after_tool_result``）的相对次序是有意为之，也是这个模块存在的理由：

- 备份发生在 ``before_tool_call`` 放行之后、真正执行之前——被拦下的调用不备份；
- 截断发生在 ``after_tool_result`` 链之前——处理器看到的就是最终写进 step、
  对话历史与 trace 的那份文本。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from dm_agent.tools.base import Tool

from .events import AfterToolResultEvent, BeforeToolCallEvent, EventBus, HookErrorHandler
from .guards import WRITE_ACTIONS
from .observation import ObservationBounder
from .persistence import RunPersistence
from .run_state import RunContext


@dataclass
class ToolInvocation:
    """一次工具调用的结果。

    ``arguments`` 可能被 ``before_tool_call`` 处理器就地改过，调用方要用返回的这份
    （step、对话历史与 trace 都以它为准）。
    """

    arguments: Any
    observation: str
    error_kind: str = ""
    blocked: bool = False
    tool_succeeded: bool = False


def coerce_task_complete_arguments(action_input: Any) -> dict[str, Any]:
    """``task_complete`` 允许模型传字符串或干脆不传参数。"""
    if action_input is None:
        return {}
    if isinstance(action_input, str):
        return {"message": action_input}
    if not isinstance(action_input, dict):
        return {}
    return action_input


def validate_tool_arguments(action_input: Any) -> tuple[str, str] | None:
    """校验普通工具的入参，返回 (failure_reason, observation)；合法时返回 None。"""
    if action_input is None:
        return "Tool arguments missing", "Tool arguments missing: action_input is null."
    if not isinstance(action_input, dict):
        return "Tool arguments must be a JSON object", "Tool arguments must be a JSON object."
    return None


class ToolInvoker:
    """按固定次序把一次工具调用跑完，并把过程记进 metadata。"""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        bounder: ObservationBounder,
        persistence: RunPersistence,
        on_error: HookErrorHandler | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.bounder = bounder
        self.persistence = persistence
        self.on_error = on_error

    def invoke(
        self,
        tool: Tool,
        *,
        action: str,
        action_input: Any,
        context: RunContext,
    ) -> ToolInvocation:
        """执行一次工具调用；入参非法或被钩子拦下时不会真正调用 runner。"""
        metadata = context.metadata
        if action == "task_complete":
            action_input = coerce_task_complete_arguments(action_input)
        else:
            invalid = validate_tool_arguments(action_input)
            if invalid is not None:
                failure_reason, observation = invalid
                metadata["argument_error_count"] += 1
                metadata["failure_reason"] = failure_reason
                return ToolInvocation(
                    arguments=action_input,
                    observation=observation,
                    error_kind="invalid_arguments",
                )

        before_event = BeforeToolCallEvent(
            tool_name=action,
            arguments=cast(dict[str, Any], action_input),
            step_number=context.step_number,
            run_id=context.run_id,
            metadata=metadata,
        )
        block = self.event_bus.emit_before_tool_call(before_event, on_error=self.on_error)
        action_input = before_event.arguments
        if block is not None:
            # 被拦下的调用不计入计划完成，也不备份。
            return ToolInvocation(
                arguments=action_input,
                observation=str(block["reason"]),
                blocked=True,
            )

        if action in WRITE_ACTIONS:
            self.persistence.backup_before_write(action_input, context)

        error_kind = ""
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

        after_event = AfterToolResultEvent(
            tool_name=action,
            arguments=action_input,
            observation=self.bounder.bound(
                raw_observation,
                action=action,
                action_input=action_input,
                context=context,
            ),
            step_number=context.step_number,
            run_id=context.run_id,
            tool_succeeded=tool_succeeded,
            metadata=metadata,
        )
        return ToolInvocation(
            arguments=action_input,
            observation=self.event_bus.emit_after_tool_result(after_event, on_error=self.on_error),
            error_kind=error_kind,
            tool_succeeded=tool_succeeded,
        )
