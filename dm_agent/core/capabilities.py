"""内核与可选能力之间的装配契约。

可选能力（Critic 门禁、工具熔断、Reflexion 重试……）不再以 ``if self.enable_xxx:``
分支的形式住在 :class:`~dm_agent.core.agent.ReactAgent` 里，而是实现本模块的
``AgentCapability`` 协议，在 Agent 装配的最后一步挂到生命周期事件总线上。

内核只通过 :class:`CapabilityContext` 暴露三样东西，不把 ``ReactAgent`` 本身交出去：

- ``event_bus``：唯一的行为接入点，能力只能通过钩子改变行为；
- ``client_for``：按 phase 包装过的 LLM 客户端工厂，保证能力自己发起的请求
  同样经过 ``before_llm_request`` 钩子；
- ``trace_writer``：可选的审计写入器，能力自己负责判空。

具体实现放在 ``dm_agent/extensions/capabilities/`` 下，与第三方扩展同层。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .events import EventBus


@dataclass(frozen=True)
class CapabilityContext:
    """能力安装时能拿到的内核资源。"""

    event_bus: EventBus
    client_for: Callable[[str], Any]
    trace_writer: Any | None = None


@runtime_checkable
class AgentCapability(Protocol):
    """可选能力的统一装配入口。

    ``install`` 在 Agent 构造末尾被调用一次，实现方在这里注册自己需要的钩子。
    注册顺序即执行顺序：能力先于内核内置守卫注册，与迁移前的判定次序一致。
    """

    def install(self, context: CapabilityContext) -> None: ...
