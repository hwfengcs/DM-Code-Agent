"""ReAct 智能体可以调用的实用工具。"""

from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List


@dataclass
class Tool:
    """表示智能体可以调用的可调用工具。"""

    name: str
    description: str
    runner: Callable[[Dict[str, Any]], str]

    def execute(self, arguments: Dict[str, Any]) -> str:
        return self.runner(arguments)


def _require_str(arguments: Dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"工具参数 '{key}' 必须是非空字符串。")
    return value.strip()


def create_file(arguments: Dict[str, Any]) -> str:
    path_value = _require_str(arguments, "path")
    content = arguments.get("content", "")
    if not isinstance(content, str):
        raise ValueError("工具参数 'content' 必须是字符串。")

    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"已将 {len(content)} 个字符写入 {path}。"


def read_file(arguments: Dict[str, Any]) -> str:
    path_value = _require_str(arguments, "path")
    path = Path(path_value)
    if not path.exists():
        return f"文件 {path} 不存在。"
    if not path.is_file():
        return f"路径 {path} 不是文件。"
    return path.read_text(encoding="utf-8")


def list_directory(arguments: Dict[str, Any]) -> str:
    path_value = arguments.get("path", ".")
    if not isinstance(path_value, str):
        raise ValueError("工具参数 'path' 如果提供必须是字符串。")
    path = Path(path_value or ".")
    if not path.exists():
        return f"目录 {path} 不存在。"
    if not path.is_dir():
        return f"路径 {path} 不是目录。"

    entries = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
    return "\n".join(entries) if entries else "<空>"


def run_python(arguments: Dict[str, Any]) -> str:
    code = arguments.get("code")
    path_value = arguments.get("path")

    if isinstance(code, str) and code.strip():
        command = [sys.executable, "-u", "-c", code]
    elif isinstance(path_value, str) and path_value.strip():
        command = [sys.executable, "-u", str(Path(path_value))]
        extra_args = arguments.get("args")
        if isinstance(extra_args, list):
            command.extend(str(item) for item in extra_args)
        elif isinstance(extra_args, str) and extra_args.strip():
            command.extend(shlex.split(extra_args))
        elif extra_args is not None:
            raise ValueError("工具参数 'args' 必须是字符串或字符串列表。")
    else:
        raise ValueError("run_python 工具需要 'code' 或 'path' 参数。")

    result = subprocess.run(command, capture_output=True, text=True)
    segments: List[str] = []
    if result.stdout:
        segments.append(result.stdout.strip())
    if result.stderr:
        segments.append(f"stderr:\n{result.stderr.strip()}")
    segments.append(f"returncode: {result.returncode}")
    return "\n".join(segment for segment in segments if segment).strip() or "returncode: 0"


def run_shell(arguments: Dict[str, Any]) -> str:
    command = _require_str(arguments, "command")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    segments: List[str] = []
    if result.stdout:
        segments.append(result.stdout.strip())
    if result.stderr:
        segments.append(f"stderr:\n{result.stderr.strip()}")
    segments.append(f"returncode: {result.returncode}")
    return "\n".join(segment for segment in segments if segment).strip() or "returncode: 0"


def task_complete(arguments: Dict[str, Any]) -> str:
    """标记任务完成的工具。调用此工具将自动结束任务。"""
    message = arguments.get("message", "")
    if message and isinstance(message, str):
        return f"任务完成：{message.strip()}"
    return "任务已完成。"


def default_tools() -> List[Tool]:
    return [
        Tool(
            name="list_directory",
            description="List entries for the given directory path. Arguments: {\"path\": optional string, defaults to '.'}.",
            runner=list_directory,
        ),
        Tool(
            name="read_file",
            description="Read a UTF-8 text file. Arguments: {\"path\": string}.",
            runner=read_file,
        ),
        Tool(
            name="create_file",
            description="Create or overwrite a text file. Arguments: {\"path\": string, \"content\": string}.",
            runner=create_file,
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
            name="task_complete",
            description="Mark the task as complete and finish execution. Arguments: {\"message\": optional string with completion summary}.",
            runner=task_complete,
        ),
    ]
