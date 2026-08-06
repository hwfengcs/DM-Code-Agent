"""工具模块 - 提供智能体可用的各类工具"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import Tool
from .code_analysis_tools import (
    find_dependencies,
    get_code_metrics,
    get_function_signature,
    parse_ast,
)
from .code_index_tools import build_code_index, dependency_graph, search_symbol
from .execution_tools import run_linter, run_python, run_shell, run_tests
from .file_tools import (
    create_file,
    edit_file,
    list_directory,
    read_file,
    search_in_file,
)

if TYPE_CHECKING:
    from dm_agent.extensions import ExtensionAPI, ExtensionRegistry


def task_complete(arguments: dict[str, Any]) -> str:
    """
    标记任务完成的工具。调用此工具将自动结束任务。

    当智能体认为任务已经完成时，应调用此工具来终止任务执行流程。
    该工具通常作为任务计划的最后一个步骤被调用。

    Args:
        arguments (Dict[str, Any]): 工具调用参数字典
            - message (str, optional): 任务完成的描述信息，默认为空字符串

    Returns:
        str: 格式化的任务完成消息
            - 如果提供了有效的message字符串，则返回 "任务完成：{message}"
            - 否则返回默认消息 "任务已完成。"

    Examples:
        >>> task_complete({"message": "数据分析已完成"})
        '任务完成：数据分析已完成'

        >>> task_complete({})
        '任务已完成。'

        >>> task_complete({"message": "  "})
        '任务已完成。'
    """
    message = ""
    for key in ("message", "answer", "final_answer", "summary", "result"):
        value = arguments.get(key, "")
        if isinstance(value, str) and value.strip():
            message = value.strip()
            break
    if message:
        return f"任务完成：{message}"
    return "任务已完成。"


def _builtin_tools() -> list[Tool]:
    """构造顺序稳定的内置工具实例。"""
    return [
        Tool(
            name="list_directory",
            description=(
                "List entries for the given directory path. Arguments: {\"path\": optional string (default '.'), "
                "\"recursive\": optional bool (default false), \"file_type\": optional string filter like '.py' or '.js'}."
            ),
            runner=list_directory,
        ),
        Tool(
            name="read_file",
            description=(
                'Read a UTF-8 text file. Arguments: {"path": string, '
                '"line_start": optional int, "line_end": optional int}.'
            ),
            runner=read_file,
        ),
        Tool(
            name="create_file",
            description='Create or overwrite a text file. Arguments: {"path": string, "content": string}.',
            runner=create_file,
        ),
        Tool(
            name="edit_file",
            description=(
                "Edit a file. PREFERRED: content-anchored replace with "
                '{"path": string, "old_string": string, "new_string": string} — '
                "old_string must match exactly once (whitespace and indentation "
                "included), and new_string must contain an actual change; if the strings "
                "are identical or old_string matches zero or several times, nothing is written. "
                "Fallback (line-numbered, use only when content anchoring will not do): "
                '{"path": string, "operation": "insert"|"replace"|"delete", '
                '"line_start": int, "line_end": int (for replace/delete), '
                '"content": string (for insert/replace)}. Line numbers shift after every '
                "edit, so re-read the file before using them again. Every edit echoes the "
                "resulting lines back to you — check them before moving on."
            ),
            runner=edit_file,
        ),
        Tool(
            name="search_in_file",
            description=(
                'Search for text or regex pattern in a file. Arguments: {"path": string, "pattern": string, '
                '"context_lines": optional int (default 2)}.'
            ),
            runner=search_in_file,
        ),
        Tool(
            name="run_python",
            description=(
                'Execute Python code using the local interpreter. Arguments: either {"code": string} or {"path": string, "args": optional string or list}.'
            ),
            runner=run_python,
        ),
        Tool(
            name="run_shell",
            description='Execute a shell command. Arguments: {"command": string}.',
            runner=run_shell,
        ),
        Tool(
            name="run_tests",
            description=(
                "Run Python test suite. Arguments: {\"test_path\": optional string (default '.'), "
                '"framework": optional "pytest"|"unittest" (default \'pytest\'), "verbose": optional bool (default false)}.'
            ),
            runner=run_tests,
        ),
        Tool(
            name="run_linter",
            description=(
                'Run code linter/formatter. Arguments: {"path": string, '
                '"tool": optional "ruff"|"flake8"|"pylint"|"mypy"|"black" (default \'ruff\')}. '
                "If the chosen linter is not installed here, the tool replies with the list "
                "of linters this environment does provide -- switch to one of those."
            ),
            runner=run_linter,
        ),
        Tool(
            name="parse_ast",
            description=(
                'Parse Python file AST to extract structure (functions, classes, imports). Arguments: {"path": string}.'
            ),
            runner=parse_ast,
        ),
        Tool(
            name="get_function_signature",
            description=(
                'Get function signature with type hints. Arguments: {"path": string, "function_name": string}.'
            ),
            runner=get_function_signature,
        ),
        Tool(
            name="find_dependencies",
            description=('Analyze file dependencies (imports). Arguments: {"path": string}.'),
            runner=find_dependencies,
        ),
        Tool(
            name="get_code_metrics",
            description=(
                'Get code metrics (lines, functions, classes count). Arguments: {"path": string}.'
            ),
            runner=get_code_metrics,
        ),
        Tool(
            name="build_code_index",
            description=(
                'Build a repository-level Python symbol index. Arguments: {"root": optional string (default "."), '
                '"max_files": optional int (default 200), "include_tests": optional bool (default true)}.'
            ),
            runner=build_code_index,
        ),
        Tool(
            name="search_symbol",
            description=(
                'Search classes, functions, and methods by name. Arguments: {"name": string, '
                '"root": optional string, "kind": optional "class"|"function"|"method", '
                '"exact": optional bool, "max_files": optional int}.'
            ),
            runner=search_symbol,
        ),
        Tool(
            name="dependency_graph",
            description=(
                'Build a local Python import dependency graph. Arguments: {"root": optional string, '
                '"max_files": optional int, "include_external": optional bool}.'
            ),
            runner=dependency_graph,
        ),
        Tool(
            name="task_complete",
            description='Mark the task as complete and finish execution. Arguments: {"message": optional string with completion summary}.',
            runner=task_complete,
        ),
    ]


def register_builtin_tools(api: ExtensionAPI) -> None:
    """通过 ExtensionAPI 注册全部内置工具。"""
    for tool in _builtin_tools():
        api.register_tool(tool)


def default_tools(
    include_mcp: bool = True,
    mcp_tools: list[Tool] | None = None,
    *,
    extension_registry: ExtensionRegistry | None = None,
) -> list[Tool]:
    """返回注册表中的工具，并保持 MCP 工具最后追加的既有行为。"""
    if extension_registry is None:
        from dm_agent.extensions.discovery import create_builtin_registry

        extension_registry = create_builtin_registry()
    tools = extension_registry.get_tools()

    if include_mcp and mcp_tools:
        tools.extend(mcp_tools)

    return tools


__all__ = [
    "Tool",
    "default_tools",
    "register_builtin_tools",
    "task_complete",
]
