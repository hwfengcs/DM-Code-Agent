"""工具模块 - 提供智能体可用的各类工具"""

from typing import Any, Dict, List

from .base import Tool
from .file_tools import (
    create_file,
    edit_file,
    list_directory,
    read_file,
    search_in_file,
)
from .execution_tools import run_linter, run_python, run_shell, run_tests


def task_complete(arguments: Dict[str, Any]) -> str:
    """标记任务完成的工具。调用此工具将自动结束任务。"""
    message = arguments.get("message", "")
    if message and isinstance(message, str):
        return f"任务完成：{message.strip()}"
    return "任务已完成。"


def default_tools() -> List[Tool]:
    """返回默认工具集"""
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
            name="task_complete",
            description="Mark the task as complete and finish execution. Arguments: {\"message\": optional string with completion summary}.",
            runner=task_complete,
        ),
    ]


__all__ = [
    "Tool",
    "default_tools",
    "task_complete",
]