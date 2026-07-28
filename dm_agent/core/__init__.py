"""核心模块 - Agent 实现"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .agent import ReactAgent, Step
from .capabilities import AgentCapability, CapabilityContext
from .critic import CriticAgent, CriticReview
from .events import (
    AfterToolResultEvent,
    BeforeFinishEvent,
    BeforeLLMRequestEvent,
    BeforeToolCallEvent,
    EventBus,
    HookFailure,
    RunEndEvent,
    RunStartEvent,
)
from .observation import is_failure_observation
from .planner import AdaptiveReplanPolicy, ReplanDecision, ReplanSignal
from .reflexion import EpisodicMemory, Lesson, Reflector

if TYPE_CHECKING:
    from dm_agent.extensions.capabilities.self_consistency import (
        SelfConsistencyCandidate,
        SelfConsistencyRunner,
    )

# self-consistency 已搬到 dm_agent/extensions/capabilities/。这里保留惰性再导出，
# 让 dm_agent.core.SelfConsistencyRunner 等旧路径继续可用，同时避免
# core 在 import 期就拉起 extensions 包（会与 core.agent 的导入相互缠绕）。
_RELOCATED = {
    "SelfConsistencyCandidate": "dm_agent.extensions.capabilities.self_consistency",
    "SelfConsistencyResult": "dm_agent.extensions.capabilities.self_consistency",
    "SelfConsistencyRunner": "dm_agent.extensions.capabilities.self_consistency",
}


def __getattr__(name: str) -> Any:
    module_path = _RELOCATED.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_path), name)


__all__ = [
    "AdaptiveReplanPolicy",
    "AfterToolResultEvent",
    "AgentCapability",
    "BeforeFinishEvent",
    "BeforeLLMRequestEvent",
    "BeforeToolCallEvent",
    "CapabilityContext",
    "CriticAgent",
    "CriticReview",
    "EpisodicMemory",
    "EventBus",
    "HookFailure",
    "Lesson",
    "ReactAgent",
    "Reflector",
    "ReplanDecision",
    "ReplanSignal",
    "RunEndEvent",
    "RunStartEvent",
    "SelfConsistencyCandidate",
    "SelfConsistencyRunner",
    "Step",
    "is_failure_observation",
]
