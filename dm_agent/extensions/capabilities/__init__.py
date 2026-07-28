"""内置可选能力：以生命周期钩子实现，与第三方扩展同层。

这些模块曾经是 ``ReactAgent`` 构造函数里的布尔分支。搬出来之后，内核不再为它们
保留任何 ``if`` 语句，CLI 开关只负责决定「安装哪些能力」。
"""

from __future__ import annotations

from .circuit_breaker_gate import CircuitBreakerGate
from .critic_gate import CriticGate
from .reflexion_loop import ReflexionLoop

__all__ = ["CircuitBreakerGate", "CriticGate", "ReflexionLoop"]
