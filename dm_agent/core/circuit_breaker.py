"""工具级熔断器（默认关闭，--enable-circuit-breaker 打开）。

同一 (action, error_kind) 组合连续失败达到阈值后进入 open 状态：后续对该
工具的调用被拦截并返回引导性观察，冷却若干步后放行一次探针（half-open），
探针成功则恢复（closed），失败则重新熔断。

键刻意不含观察文本前缀——比 ``_failure_signature`` 粗一档，这样 P1 的
截断/文案变化不会影响熔断判定。拦截文案避开失败关键词，不触发 replan。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


@dataclass
class _BreakerEntry:
    consecutive_failures: int = 0
    state: str = STATE_CLOSED
    opened_at_step: int = 0
    trip_count: int = 0


class ToolCircuitBreaker:
    """按 (action, error_kind) 熔断反复失败的工具调用。"""

    def __init__(self, *, threshold: int = 3, cooldown_steps: int = 5) -> None:
        if threshold < 2:
            raise ValueError("threshold must be at least 2")
        if cooldown_steps < 1:
            raise ValueError("cooldown_steps must be at least 1")
        self.threshold = threshold
        self.cooldown_steps = cooldown_steps
        self._entries: Dict[str, _BreakerEntry] = {}
        self._last_error_kind: Dict[str, str] = {}

    @staticmethod
    def _key(action: str, error_kind: str) -> str:
        return f"{action}|{error_kind or 'unknown'}"

    def intercept(self, action: str, step: int) -> Optional[str]:
        """open 状态下返回拦截观察；允许执行（含探针放行）时返回 None。"""
        error_kind = self._last_error_kind.get(action, "")
        entry = self._entries.get(self._key(action, error_kind))
        if entry is None or entry.state != STATE_OPEN:
            return None
        if step - entry.opened_at_step >= self.cooldown_steps:
            entry.state = STATE_HALF_OPEN
            return None
        reopen_step = entry.opened_at_step + self.cooldown_steps
        return (
            f"Tool {action} is temporarily disabled after "
            f"{entry.consecutive_failures} repeated identical outcomes; try a different "
            f"tool or approach. One probe attempt will be allowed at step {reopen_step}."
        )

    def record(self, action: str, error_kind: str, *, failed: bool, step: int) -> str:
        """记录一次执行结果，返回该组合的最新状态。

        成功会清零该 action 下所有错误类别的计数（探针成功 = 完全恢复，
        后续失败需要重新累计到阈值才会再次熔断）。
        """
        if not failed:
            self._last_error_kind[action] = ""
            prefix = f"{action}|"
            for key, entry in self._entries.items():
                if key.startswith(prefix):
                    entry.consecutive_failures = 0
                    entry.state = STATE_CLOSED
            return STATE_CLOSED
        self._last_error_kind[action] = error_kind or ""
        entry = self._entries.setdefault(self._key(action, error_kind), _BreakerEntry())
        entry.consecutive_failures += 1
        if entry.state == STATE_HALF_OPEN or entry.consecutive_failures >= self.threshold:
            entry.state = STATE_OPEN
            entry.opened_at_step = step
            entry.trip_count += 1
        return entry.state

    def status(self, action: str, error_kind: str = "") -> _BreakerEntry:
        return self._entries.get(
            self._key(action, error_kind or self._last_error_kind.get(action, "")),
            _BreakerEntry(),
        )

    @property
    def total_trips(self) -> int:
        return sum(entry.trip_count for entry in self._entries.values())

    def snapshot(self) -> Dict[str, Dict[str, int | str]]:
        return {
            key: {
                "state": entry.state,
                "consecutive_failures": entry.consecutive_failures,
                "trip_count": entry.trip_count,
            }
            for key, entry in self._entries.items()
        }
