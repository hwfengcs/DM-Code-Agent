"""Agent 生命周期事件与同步中间件事件总线。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

EventName = Literal["before_tool_call", "after_tool_result", "before_llm_request"]
HookErrorHandler = Callable[["HookFailure"], None]


@dataclass
class BeforeToolCallEvent:
    """工具执行前事件。

    处理器可以就地修改 ``arguments``。事件链结束后不会重新做参数校验，
    工具会直接收到修改后的参数；这是刻意保留的中间件语义。
    """

    tool_name: str
    arguments: dict[str, Any]
    step_number: int
    run_id: str
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class AfterToolResultEvent:
    """工具执行后事件，后续处理器会看到前序处理器改写的 observation。"""

    tool_name: str
    arguments: dict[str, Any]
    observation: str
    step_number: int
    run_id: str
    tool_succeeded: bool
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class BeforeLLMRequestEvent:
    """一次逻辑 LLM 请求发出前的事件。"""

    messages: list[dict[str, str]]
    step_number: int
    run_id: str
    phase: str
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class HookFailure:
    """单个处理器失败的可审计描述。"""

    hook: EventName
    handler: str
    handler_position: int
    step_number: int
    run_id: str
    error_type: str
    message: str
    tool_name: str = ""
    phase: str = ""

    def to_trace_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "hook": self.hook,
            "handler": self.handler,
            "handler_position": self.handler_position,
            "step_number": self.step_number,
            "run_id": self.run_id,
            "error_type": self.error_type,
            "message": self.message,
        }
        if self.tool_name:
            payload["tool_name"] = self.tool_name
        if self.phase:
            payload["phase"] = self.phase
        return payload


@dataclass(frozen=True)
class _RegisteredHandler:
    name: str
    callback: Callable[[Any], Any]


class EventBus:
    """按注册顺序串联处理器的同步事件总线。

    每个处理器的输出都会成为下一个处理器的输入。单个处理器抛异常或返回
    非法结果时，只上报该处理器的失败并继续事件链，不会中断 Agent run。
    """

    _EVENT_NAMES = frozenset({"before_tool_call", "after_tool_result", "before_llm_request"})

    def __init__(self) -> None:
        self._handlers: dict[str, list[_RegisteredHandler]] = {
            event_name: [] for event_name in self._EVENT_NAMES
        }

    def on(
        self,
        event: EventName,
        handler: Callable[[Any], Any],
        *,
        name: str | None = None,
    ) -> None:
        """注册处理器；同一事件严格按调用 ``on`` 的顺序执行。"""
        if event not in self._EVENT_NAMES:
            raise ValueError(f"Unsupported lifecycle event: {event}")
        handler_name = name.strip() if isinstance(name, str) else ""
        if not handler_name:
            handler_name = _handler_name(handler)
        self._handlers[event].append(_RegisteredHandler(handler_name, handler))

    def emit_before_tool_call(
        self,
        event: BeforeToolCallEvent,
        *,
        on_error: HookErrorHandler | None = None,
    ) -> dict[str, Any] | None:
        """执行工具前置链；遇到第一个 ``block=True`` 时停止并返回。"""
        for position, handler in enumerate(self._handlers["before_tool_call"], start=1):
            previous_arguments = dict(event.arguments)
            succeeded, result = self._call("before_tool_call", handler, position, event, on_error)
            if not succeeded:
                event.arguments = previous_arguments
                continue
            if result is None:
                continue
            if not isinstance(result, Mapping):
                event.arguments = previous_arguments
                self._report_invalid_result(
                    "before_tool_call", handler, position, event, result, on_error
                )
                continue
            if bool(result.get("block")):
                reason = str(result.get("reason") or "Tool call blocked by lifecycle handler.")
                return {"block": True, "reason": reason}
        return None

    def emit_after_tool_result(
        self,
        event: AfterToolResultEvent,
        *,
        on_error: HookErrorHandler | None = None,
    ) -> str:
        """串联改写 observation，返回最终结果。"""
        for position, handler in enumerate(self._handlers["after_tool_result"], start=1):
            previous = event.observation
            succeeded, result = self._call("after_tool_result", handler, position, event, on_error)
            if not succeeded:
                event.observation = previous
                continue
            candidate = event.observation if result is None else result
            if not isinstance(candidate, str):
                event.observation = previous
                self._report_invalid_result(
                    "after_tool_result", handler, position, event, candidate, on_error
                )
                continue
            event.observation = candidate
        return event.observation

    def emit_before_llm_request(
        self,
        event: BeforeLLMRequestEvent,
        *,
        on_error: HookErrorHandler | None = None,
    ) -> list[dict[str, str]]:
        """串联改写 messages，返回实际发送给客户端的消息。"""
        for position, handler in enumerate(self._handlers["before_llm_request"], start=1):
            previous = [dict(message) for message in event.messages]
            succeeded, result = self._call("before_llm_request", handler, position, event, on_error)
            if not succeeded:
                event.messages = previous
                continue
            candidate = event.messages if result is None else result
            if not _valid_messages(candidate):
                event.messages = previous
                self._report_invalid_result(
                    "before_llm_request", handler, position, event, candidate, on_error
                )
                continue
            event.messages = candidate
        return event.messages

    def _call(
        self,
        event_name: EventName,
        handler: _RegisteredHandler,
        position: int,
        event: Any,
        on_error: HookErrorHandler | None,
    ) -> tuple[bool, Any]:
        try:
            return True, handler.callback(event)
        except Exception as exc:
            self._report_failure(event_name, handler, position, event, exc, on_error)
            return False, None

    def _report_invalid_result(
        self,
        event_name: EventName,
        handler: _RegisteredHandler,
        position: int,
        event: Any,
        result: Any,
        on_error: HookErrorHandler | None,
    ) -> None:
        error = TypeError(f"Handler returned unsupported result type: {type(result).__name__}")
        self._report_failure(event_name, handler, position, event, error, on_error)

    @staticmethod
    def _report_failure(
        event_name: EventName,
        handler: _RegisteredHandler,
        position: int,
        event: Any,
        error: Exception,
        on_error: HookErrorHandler | None,
    ) -> None:
        if on_error is None:
            return
        failure = HookFailure(
            hook=event_name,
            handler=handler.name,
            handler_position=position,
            step_number=int(getattr(event, "step_number", 0)),
            run_id=str(getattr(event, "run_id", "")),
            tool_name=str(getattr(event, "tool_name", "")),
            phase=str(getattr(event, "phase", "")),
            error_type=type(error).__name__,
            message=str(error),
        )
        try:
            on_error(failure)
        except Exception:
            # trace 写入也是 best effort，不能反过来破坏异常隔离保证。
            return


class LLMRequestClient:
    """在一次逻辑 ``respond`` 调用前应用消息中间件的轻量代理。"""

    def __init__(
        self,
        client: Any,
        event_bus: EventBus,
        context_provider: Callable[[], tuple[str, int, dict[str, Any]]],
        on_error: HookErrorHandler | None,
        *,
        phase: str = "agent",
    ) -> None:
        self._client = client
        self._event_bus = event_bus
        self._context_provider = context_provider
        self._on_error = on_error
        self._phase = phase

    def with_phase(self, phase: str) -> LLMRequestClient:
        return LLMRequestClient(
            self._client,
            self._event_bus,
            self._context_provider,
            self._on_error,
            phase=phase,
        )

    def respond(self, messages: list[dict[str, str]], **extra: Any) -> str:
        run_id, step_number, metadata = self._context_provider()
        event = BeforeLLMRequestEvent(
            messages=[dict(message) for message in messages],
            step_number=step_number,
            run_id=run_id,
            phase=self._phase,
            metadata=metadata,
        )
        outgoing = self._event_bus.emit_before_llm_request(event, on_error=self._on_error)
        # 调用者随后会用同一列表写 trace；原地替换可确保 trace 与真实请求一致，
        # 同时浅复制消息字典，避免处理器意外污染 conversation_history。
        messages[:] = outgoing
        return str(self._client.respond(messages, **extra))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def _handler_name(handler: Callable[[Any], Any]) -> str:
    module = str(getattr(handler, "__module__", ""))
    qualname = str(getattr(handler, "__qualname__", handler.__class__.__qualname__))
    return f"{module}.{qualname}" if module else qualname


def _valid_messages(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return all(
        isinstance(message, dict)
        and isinstance(message.get("role"), str)
        and isinstance(message.get("content"), str)
        for message in value
    )
