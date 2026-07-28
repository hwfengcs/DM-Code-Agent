"""扩展可见 API 与内核侧注册表。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from dm_agent.core.events import EventBus, EventName
    from dm_agent.skills.base import BaseSkill
    from dm_agent.tools.base import Tool

ProviderFactory = Callable[..., Any]
EventHandler = Callable[[Any], Any]
ExtensionSetup = Callable[["ExtensionAPI"], None]

_SUPPORTED_EVENTS = frozenset(
    {
        "before_tool_call",
        "after_tool_result",
        "before_llm_request",
        "before_finish",
        "on_run_start",
        "on_run_end",
    }
)


@dataclass(frozen=True)
class _EventRegistration:
    event: str
    handler: EventHandler
    source: str


class ExtensionRegistry:
    """保存一次运行所需的工具、技能、供应商与事件处理器。

    同名工具、技能和供应商采用后注册覆盖前注册的规则。字典中的原始位置保持
    不变，因此覆盖内置项不会改变默认工具提示词或技能选择的稳定顺序。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._skills: dict[str, BaseSkill] = {}
        self._providers: dict[str, ProviderFactory] = {}
        self._event_handlers: list[_EventRegistration] = []

    def api(self, source: str) -> ExtensionAPI:
        """为一个扩展创建只暴露四个注册方法的接口。"""
        normalized_source = source.strip() or "extension"
        return ExtensionAPI(self, normalized_source)

    def apply_setup(self, setup: ExtensionSetup, *, source: str) -> None:
        """事务式执行一个扩展的 setup，失败时不保留部分注册结果。"""
        if not callable(setup):
            raise TypeError("Extension setup must be callable.")
        staged = ExtensionRegistry()
        setup(staged.api(source))
        self._tools.update(staged._tools)
        self._skills.update(staged._skills)
        self._providers.update(staged._providers)
        self._event_handlers.extend(staged._event_handlers)

    def get_tools(self) -> list[Tool]:
        """按稳定注册顺序返回去重后的工具。"""
        return list(self._tools.values())

    def get_skills(self) -> list[BaseSkill]:
        """按稳定注册顺序返回去重后的技能。"""
        return list(self._skills.values())

    def get_provider_factory(self, name: str) -> ProviderFactory | None:
        """返回规范化名称对应的供应商工厂。"""
        return self._providers.get(_provider_name(name))

    def get_provider_names(self) -> list[str]:
        """按稳定注册顺序返回供应商名称。"""
        return list(self._providers)

    def create_event_bus(self) -> EventBus:
        """为一个 Agent 物化独立事件总线，避免内置处理器跨实例累积。"""
        from dm_agent.core.events import EventBus

        event_bus = EventBus()
        for registration in self._event_handlers:
            event_bus.on(
                cast("EventName", registration.event),
                registration.handler,
                name=_event_handler_name(registration),
            )
        return event_bus

    def _register_tool(self, tool: Tool) -> None:
        name = str(getattr(tool, "name", "")).strip()
        if not name:
            raise ValueError("Extension tools must have a non-empty name.")
        self._tools[name] = tool

    def _register_skill(self, skill: BaseSkill) -> None:
        metadata = skill.get_metadata()
        name = str(getattr(metadata, "name", "")).strip()
        if not name:
            raise ValueError("Extension skills must have a non-empty metadata name.")
        self._skills[name] = skill

    def _register_provider(self, name: str, factory: ProviderFactory) -> None:
        if not callable(factory):
            raise TypeError("Extension provider factory must be callable.")
        self._providers[_provider_name(name)] = factory

    def _register_event(self, event: str, handler: EventHandler, source: str) -> None:
        if event not in _SUPPORTED_EVENTS:
            raise ValueError(f"Unsupported lifecycle event: {event}")
        if not callable(handler):
            raise TypeError("Extension event handler must be callable.")
        self._event_handlers.append(_EventRegistration(event, handler, source))


class ExtensionAPI:
    """扩展模块拿到的唯一接口；不会暴露 ReactAgent 或其他内核对象。"""

    __slots__ = ("__registry", "__source")

    def __init__(self, registry: ExtensionRegistry, source: str) -> None:
        self.__registry = registry
        self.__source = source

    def register_tool(self, tool: Tool) -> None:
        """注册或覆盖同名工具。"""
        self.__registry._register_tool(tool)

    def register_skill(self, skill: BaseSkill) -> None:
        """注册或覆盖同名技能。"""
        self.__registry._register_skill(skill)

    def register_provider(self, name: str, factory: ProviderFactory) -> None:
        """注册或覆盖名称不区分大小写的 LLM 供应商。"""
        self.__registry._register_provider(name, factory)

    def on(self, event: str, handler: EventHandler) -> None:
        """按扩展加载顺序注册生命周期事件处理器。"""
        self.__registry._register_event(event, handler, self.__source)


def _provider_name(name: str) -> str:
    normalized = name.strip().casefold()
    if not normalized:
        raise ValueError("Extension provider name must not be empty.")
    return normalized


def _event_handler_name(registration: _EventRegistration) -> str:
    handler = registration.handler
    module = str(getattr(handler, "__module__", ""))
    qualname = str(getattr(handler, "__qualname__", handler.__class__.__qualname__))
    callback_name = f"{module}.{qualname}" if module else qualname
    return f"{registration.source}:{callback_name}"
