"""工具模块 - 提供智能体可用的各类工具"""

from typing import Any, Dict, List, Optional

from .base import Tool
from .file_tools import (
    create_file,
    edit_file,
    list_directory,
    read_file,
    search_in_file,
)
from .execution_tools import run_linter, run_python, run_shell, run_tests
from .code_analysis_tools import (
    parse_ast,
    get_function_signature,
    find_dependencies,
    get_code_metrics,
)


def task_complete(arguments: Dict[str, Any]) -> str:
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
    message = arguments.get("message", "")
    if message and isinstance(message, str):
        return f"任务完成：{message.strip()}"
    return "任务已完成。"


def default_tools(include_mcp: bool = True, mcp_tools: Optional[List[Tool]] = None) -> List[Tool]:
    """返回默认工具集

    Args:
        include_mcp (bool): 是否包含 MCP 工具
        mcp_tools (Optional[List[Tool]]): MCP 工具列表（可选）

    Returns:
        tools (List[Tool]): 默认工具列表
    """
    tools = [
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
                "Read a UTF-8 text file. Arguments: {\"path\": string, "
                "\"line_start\": optional int, \"line_end\": optional int}."
            ),
            runner=read_file,
        ),
        Tool(
            name="create_file",
            description="Create or overwrite a text file. Arguments: {\"path\": string, \"content\": string}.",
            runner=create_file,
        ),
        Tool(
            name="edit_file",
            description=(
                "Edit specific lines in a file. Arguments: {\"path\": string, \"operation\": \"insert\"|\"replace\"|\"delete\", "
                "\"line_start\": int, \"line_end\": int (for replace/delete), \"content\": string (for insert/replace)}."
            ),
            runner=edit_file,
        ),
        Tool(
            name="search_in_file",
            description=(
                "Search for text or regex pattern in a file. Arguments: {\"path\": string, \"pattern\": string, "
                "\"context_lines\": optional int (default 2)}."
            ),
            runner=search_in_file,
        ),
        Tool(
            name="run_python",
            description=(
                "Execute Python code using the local interpreter. Arguments: either {\"code\": string} or {\"path\": string, \"args\": optional string or list}."
            ),
            runner=run_python,
        ),
        Tool(
            name="run_shell",
            description="Execute a shell command. Arguments: {\"command\": string}.",
            runner=run_shell,
        ),
        Tool(
            name="run_tests",
            description=(
                "Run Python test suite. Arguments: {\"test_path\": optional string (default '.'), "
                "\"framework\": optional \"pytest\"|\"unittest\" (default 'pytest'), \"verbose\": optional bool (default false)}."
            ),
            runner=run_tests,
        ),
        Tool(
            name="run_linter",
            description=(
                "Run code linter/formatter. Arguments: {\"path\": string, "
                "\"tool\": optional \"pylint\"|\"flake8\"|\"mypy\"|\"black\" (default 'flake8')}."
            ),
            runner=run_linter,
        ),
        Tool(
            name="parse_ast",
            description=(
                "Parse Python file AST to extract structure (functions, classes, imports). Arguments: {\"path\": string}."
            ),
            runner=parse_ast,
        ),
        Tool(
            name="get_function_signature",
            description=(
                "Get function signature with type hints. Arguments: {\"path\": string, \"function_name\": string}."
            ),
            runner=get_function_signature,
        ),
        Tool(
            name="find_dependencies",
            description=(
                "Analyze file dependencies (imports). Arguments: {\"path\": string}."
            ),
            runner=find_dependencies,
        ),
        Tool(
            name="get_code_metrics",
            description=(
                "Get code metrics (lines, functions, classes count). Arguments: {\"path\": string}."
            ),
            runner=get_code_metrics,
        ),
        Tool(
            name="task_complete",
            description="Mark the task as complete and finish execution. Arguments: {\"message\": optional string with completion summary}.",
            runner=task_complete,
        ),
    ]

    # 添加 MCP 工具
    if include_mcp and mcp_tools:
        tools.extend(mcp_tools)

    return tools


__all__ = [
    "Tool",
    "default_tools",
    "task_complete",
]
