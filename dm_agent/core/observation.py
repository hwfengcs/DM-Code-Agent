"""观察结果的判定与边界处理。

``is_failure_observation`` 从 ``ReactAgent._is_failure_observation`` 提出来，让不住在
内核里的能力（例如工具熔断）也能复用同一份失败判定，而不必反向 import ReactAgent。
``ReactAgent._is_failure_observation`` 保留为指向本函数的薄委托，公开行为不变。

``ObservationBounder`` 是内核护栏：它先于 ``after_tool_result`` 钩子链执行，
保证模型、对话历史与 trace 看到的是同一份（可能已截断的）文本。

判定分层的由来：观察里混着两种东西——工具**自述**的状态（"文件 X 不存在。"）和工具
**搬运**的外部内容（文件正文、子进程 stdout）。早期实现对两者一视同仁地全文扫描
``FAILURE_MARKERS``，于是读到一行 ``from errors import NotFound`` 就把一次成功的
read_file 判成失败，白烧一次重规划。``is_failure_observation`` 因此改为按来源分层，
只在工具自述的位置上判定；搬运来的正文不再参与。
"""

from __future__ import annotations

import re
from typing import Any

from dm_agent.memory.context_budget import truncate_observation

from .run_state import RunContext

# 兜底用的失败标记。措辞约束见 memory/context_budget 模块文档：内核生成的护栏文案
# （截断标记、守卫拒绝）都刻意避开这些词。
#
# 只有**未知来源**的观察（第三方扩展工具，输出格式内核无从保证）才会走这份清单做
# 全文扫描。内置工具走下面的精确判定——裸子串 "error" 匹配文件正文的误判就出在这里。
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

# 内核自己写在观察最前面的失败自述，永远位于开头。
_KERNEL_FAILURE_PREFIXES = (
    "Tool execution failed",
    "Unknown tool",
    "Tool arguments",
    "Agent response parse failed",
    "Critic rejected",
    "Critic review failed",
)

# 写入落盘了但代码语法是坏的（edit_file/create_file 的 "只报告不回滚"）：仍须重规划。
_SYNTAX_FAILURE_MARK = "[语法检查] 未通过："

# 子进程退出码。execution_tools 统一把它作为独占一行的末段写进观察，因此锚定行首行尾，
# 避免匹配到被读取的测试代码里的 `assert result.returncode == 1`。
_RETURNCODE_RE = re.compile(r"^returncode:\s*(-?\d+)\s*$", re.MULTILINE)

# 内置工具在「没能完成本次请求」时返回的自述句式。这些句子整条就是观察全文，
# 不夹带被读取的文件内容，因此可以安全地按前缀判定。
_TOOL_REFUSAL_RE = re.compile(
    r"^(?:文件|路径|目录|测试路径) .+ (?:不存在|不是文件|不是目录)。"
    r"|^(?:起始行号|行号范围|行号) .+ 超出文件范围"
    r"|^正则表达式错误："
)

# 观察格式由本仓库保证的内置工具（与 tools/__init__.py:_builtin_tools() 对齐，
# 由 tests/test_observation_failure.py 断言不漏）。对它们来说，不匹配上面任何一条
# 失败句式就是成功回执或搬运内容，不再全文扫描。
_STRUCTURED_OUTPUT_TOOLS = frozenset(
    {
        "list_directory",
        "read_file",
        "create_file",
        "edit_file",
        "search_in_file",
        "run_python",
        "run_shell",
        "run_tests",
        "run_linter",
        "parse_ast",
        "get_function_signature",
        "find_dependencies",
        "get_code_metrics",
        "build_code_index",
        "search_symbol",
        "dependency_graph",
        "task_complete",
    }
)


def is_failure_observation(observation: str, *, action: str | None = None) -> bool:
    """这条观察是否代表一次失败（进而触发重规划）。

    ``action`` 是产生该观察的工具名。传了内置工具名时走精确判定；省略或传第三方
    工具名时退回保守的全文扫描，既有调用方行为不变。
    """
    text = str(observation or "")
    if text.startswith(_KERNEL_FAILURE_PREFIXES):
        return True
    if _SYNTAX_FAILURE_MARK in text:
        return True
    matches = _RETURNCODE_RE.findall(text)
    if matches:
        # 退出码是权威信号，压过正文里出现的任何 "error"/"Traceback" 字样——
        # 那可能只是探测脚本自己打印的预期输出。
        return matches[-1] != "0"
    if _TOOL_REFUSAL_RE.search(text):
        return True
    if action in _STRUCTURED_OUTPUT_TOOLS:
        return False
    return any(marker in text for marker in FAILURE_MARKERS)


class ObservationBounder:
    """按字符上限截断观察，并把截断事实记进 metadata 与 trace。"""

    def __init__(self, *, max_chars: int, trace_writer: Any | None = None) -> None:
        self.max_chars = max_chars
        self.trace_writer = trace_writer

    def bound(
        self,
        observation: Any,
        *,
        action: str,
        action_input: Any,
        context: RunContext,
    ) -> str:
        """截断超长观察并记录审计信息；模型、历史与 trace 看到同一份文本。"""
        result = truncate_observation(
            str(observation),
            max_chars=self.max_chars,
            action=action,
            action_input=action_input,
        )
        if result.truncated:
            metadata = context.metadata
            metadata["truncation_count"] += 1
            metadata["truncated_chars_saved"] += result.original_chars - result.kept_chars
            if self.trace_writer:
                self.trace_writer.record(
                    "observation_truncated",
                    {
                        "step_number": context.step_number,
                        "action": action,
                        "original_chars": result.original_chars,
                        "kept_chars": result.kept_chars,
                        "original_lines": result.original_lines,
                    },
                )
        return result.text
