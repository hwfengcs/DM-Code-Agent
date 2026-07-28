"""观察结果的判定与边界处理。

``is_failure_observation`` 从 ``ReactAgent._is_failure_observation`` 提出来，让不住在
内核里的能力（例如工具熔断）也能复用同一份失败判定，而不必反向 import ReactAgent。
``ReactAgent._is_failure_observation`` 保留为指向本函数的薄委托，公开行为不变。
"""

from __future__ import annotations

# 判定一条观察是否代表失败。措辞约束见 memory/context_budget 模块文档：
# 内核生成的护栏文案（截断标记、守卫拒绝、熔断拦截）都刻意避开这些词。
FAILURE_MARKERS = (
    "Tool execution failed",
    "Unknown tool",
    "Tool arguments",
    "parse failed",
    "Critic rejected",
    "Critic review failed",
    "returncode: 1",
    "error",
    "Error",
    "Traceback",
    "失败",
    "错误",
    "不存在",
)


def is_failure_observation(observation: str) -> bool:
    """观察文本里是否出现失败标记。"""
    return any(marker in observation for marker in FAILURE_MARKERS)
