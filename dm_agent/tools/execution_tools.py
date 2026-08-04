"""代码执行工具"""

from __future__ import annotations

import shlex
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from .base import _require_str

# run_linter 支持的检查器，按推荐顺序（ruff 最快且覆盖面最广）。
_LINTER_TOOLS = ("ruff", "flake8", "pylint", "mypy", "black")


def available_linters() -> list[str]:
    """探测当前解释器里实际装了哪些检查器，不启动子进程。"""
    available: list[str] = []
    for name in _LINTER_TOOLS:
        try:
            if find_spec(name) is not None:
                available.append(name)
        except (ImportError, ValueError):
            continue
    return available


def run_python(arguments: dict[str, Any]) -> str:
    """运行 Python 代码或脚本"""
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

    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    segments: list[str] = []
    if result.stdout:
        segments.append(result.stdout.strip())
    if result.stderr:
        segments.append(f"stderr:\n{result.stderr.strip()}")
    segments.append(f"returncode: {result.returncode}")
    return "\n".join(segment for segment in segments if segment).strip() or "returncode: 0"


def run_shell(arguments: dict[str, Any]) -> str:
    """运行 Shell 命令"""
    command = _require_str(arguments, "command")
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    segments: list[str] = []
    if result.stdout:
        segments.append(result.stdout.strip())
    if result.stderr:
        segments.append(f"stderr:\n{result.stderr.strip()}")
    segments.append(f"returncode: {result.returncode}")
    return "\n".join(segment for segment in segments if segment).strip() or "returncode: 0"


def run_tests(arguments: dict[str, Any]) -> str:
    """运行 Python 测试套件（支持 pytest 和 unittest）"""
    test_path = arguments.get("test_path", ".")
    framework = arguments.get("framework", "pytest")
    verbose = arguments.get("verbose", False)

    if not isinstance(test_path, str):
        raise ValueError("test_path 必须是字符串。")

    if framework not in ["pytest", "unittest"]:
        raise ValueError("framework 必须是 'pytest' 或 'unittest'。")

    path = Path(test_path)
    if not path.exists():
        return f"测试路径 {path} 不存在。"

    if framework == "pytest":
        command = [sys.executable, "-m", "pytest"]
        if verbose:
            command.append("-v")
        command.append(str(path))
    else:  # unittest
        command = [sys.executable, "-m", "unittest"]
        if verbose:
            command.append("-v")
        if path.is_file():
            # 转换为模块路径
            module_path = str(path).replace("/", ".").replace("\\", ".").replace(".py", "")
            command.append(module_path)
        else:
            command.extend(["discover", "-s", str(path)])

    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    segments: list[str] = []

    if result.stdout:
        segments.append(result.stdout.strip())
    if result.stderr:
        segments.append(f"stderr:\n{result.stderr.strip()}")
    segments.append(f"returncode: {result.returncode}")

    output = "\n".join(segment for segment in segments if segment).strip()
    return output if output else "returncode: 0"


def run_linter(arguments: dict[str, Any]) -> str:
    """运行代码检查工具（支持 ruff、pylint、flake8、mypy、black）"""
    path_value = _require_str(arguments, "path")
    tool = arguments.get("tool", "ruff")

    if tool not in _LINTER_TOOLS:
        raise ValueError(
            "tool 必须是 " + "、".join(f"'{name}'" for name in _LINTER_TOOLS) + " 之一。"
        )

    path = Path(path_value)
    if not path.exists():
        return f"路径 {path} 不存在。"

    if tool == "black":
        # black 用于格式化，添加 --check 只检查不修改
        command = [sys.executable, "-m", tool, "--check", str(path)]
    elif tool == "ruff":
        command = [sys.executable, "-m", tool, "check", str(path)]
    else:
        command = [sys.executable, "-m", tool, str(path)]

    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )

    # 当前解释器没装这个检查器。直接把子进程的 "No module named X" 回给模型，会让它
    # 逐个盲试下一个（实测一道题平均撞两次），因此改为报出本环境实际可用的清单。
    # 文案刻意避开 core/observation.py 的失败标记：换一个检查器重试是局部纠正，
    # 不该白烧一次完整重规划。
    if result.returncode != 0 and f"No module named {tool}" in (result.stderr or ""):
        available = [name for name in available_linters() if name != tool]
        if available:
            return (
                f"当前环境未提供 {tool}。可用的检查工具：{'、'.join(available)}，"
                f"请改用其中之一重试。"
            )
        return f"当前环境未提供 {tool}，也没有其他可用的检查工具，本步可跳过。"

    segments: list[str] = []

    if result.stdout:
        segments.append(result.stdout.strip())
    if result.stderr:
        segments.append(f"stderr:\n{result.stderr.strip()}")
    segments.append(f"returncode: {result.returncode}")

    output = "\n".join(segment for segment in segments if segment).strip()
    if output:
        return output
    return f"{tool} 检查通过，未发现问题。"
