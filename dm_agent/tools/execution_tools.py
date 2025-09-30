"""代码执行工具"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from .base import _require_str


def run_python(arguments: Dict[str, Any]) -> str:
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

    result = subprocess.run(command, capture_output=True, text=True)
    segments: List[str] = []
    if result.stdout:
        segments.append(result.stdout.strip())
    if result.stderr:
        segments.append(f"stderr:\n{result.stderr.strip()}")
    segments.append(f"returncode: {result.returncode}")
    return "\n".join(segment for segment in segments if segment).strip() or "returncode: 0"


def run_shell(arguments: Dict[str, Any]) -> str:
    """运行 Shell 命令"""
    command = _require_str(arguments, "command")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    segments: List[str] = []
    if result.stdout:
        segments.append(result.stdout.strip())
    if result.stderr:
        segments.append(f"stderr:\n{result.stderr.strip()}")
    segments.append(f"returncode: {result.returncode}")
    return "\n".join(segment for segment in segments if segment).strip() or "returncode: 0"


def run_tests(arguments: Dict[str, Any]) -> str:
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

    result = subprocess.run(command, capture_output=True, text=True)
    segments: List[str] = []

    if result.stdout:
        segments.append(result.stdout.strip())
    if result.stderr:
        segments.append(f"stderr:\n{result.stderr.strip()}")
    segments.append(f"returncode: {result.returncode}")

    output = "\n".join(segment for segment in segments if segment).strip()
    return output if output else "returncode: 0"


def run_linter(arguments: Dict[str, Any]) -> str:
    """运行代码检查工具（支持 pylint、flake8、mypy、black）"""
    path_value = _require_str(arguments, "path")
    tool = arguments.get("tool", "flake8")

    if tool not in ["pylint", "flake8", "mypy", "black"]:
        raise ValueError("tool 必须是 'pylint'、'flake8'、'mypy' 或 'black' 之一。")

    path = Path(path_value)
    if not path.exists():
        return f"路径 {path} 不存在。"

    if tool == "black":
        # black 用于格式化，添加 --check 只检查不修改
        command = [sys.executable, "-m", tool, "--check", str(path)]
    else:
        command = [sys.executable, "-m", tool, str(path)]

    result = subprocess.run(command, capture_output=True, text=True)
    segments: List[str] = []

    if result.stdout:
        segments.append(result.stdout.strip())
    if result.stderr:
        segments.append(f"stderr:\n{result.stderr.strip()}")
    segments.append(f"returncode: {result.returncode}")

    output = "\n".join(segment for segment in segments if segment).strip()
    if output:
        return output
    return f"{tool} 检查通过，未发现问题。"