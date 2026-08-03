"""内置可选能力：以生命周期钩子实现，与第三方扩展同层。

这些模块曾经是 ``ReactAgent`` 构造函数里的布尔分支。搬出来之后，内核不再为它们
保留任何 ``if`` 语句，CLI 开关只负责决定「安装哪些能力」。
"""

from __future__ import annotations

from dm_agent.core.capabilities import AgentCapability

from .circuit_breaker_gate import CircuitBreakerGate


def builtin_capabilities_for(
    *,
    enable_circuit_breaker: bool = False,
    circuit_breaker_threshold: int = 3,
    circuit_breaker_cooldown: int = 5,
) -> list[AgentCapability]:
    """把 ``ReactAgent`` 保留的旧构造参数翻译成等价的内置能力实例。

    过渡策略：``--enable-circuit-breaker`` 等 CLI 开关及其对应的构造参数语义
    完全不变，只是内部改为「安装对应的内置扩展」。这层翻译属于扩展侧而非内核，
    所以住在这里而不是 ``ReactAgent`` 里。

    返回顺序即钩子注册顺序，不要随意调整。
    """
    builtin: list[AgentCapability] = []
    if enable_circuit_breaker:
        builtin.append(
            CircuitBreakerGate(
                threshold=circuit_breaker_threshold,
                cooldown_steps=circuit_breaker_cooldown,
            )
        )
    return builtin


__all__ = [
    "CircuitBreakerGate",
    "builtin_capabilities_for",
]
