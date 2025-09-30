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
    line_start = arguments.get("line_start")
    line_end = arguments.get("line_end")

    path = Path(path_value)
    if not path.exists():
        return f"文件 {path} 不存在。"
    if not path.is_file():
        return f"路径 {path} 不是文件。"

    content = path.read_text(encoding="utf-8")

    # 如果没有指定行号范围，返回全部内容
    if line_start is None and line_end is None:
        return content

    # 处理行号范围
    lines = content.splitlines()

    if line_start is not None:
        if not isinstance(line_start, int) or line_start < 1:
            raise ValueError("line_start 必须是大于 0 的整数。")
        start_idx = line_start - 1
    else:
        start_idx = 0

    if line_end is not None:
        if not isinstance(line_end, int) or line_end < 1:
            raise ValueError("line_end 必须是大于 0 的整数。")
        if line_start and line_end < line_start:
            raise ValueError("line_end 必须大于等于 line_start。")
        end_idx = line_end
    else:
        end_idx = len(lines)

    if start_idx >= len(lines):
        return f"起始行号 {line_start} 超出文件范围（共 {len(lines)} 行）。"

    selected_lines = lines[start_idx:end_idx]
    return "\n".join(selected_lines)


def list_directory(arguments: Dict[str, Any]) -> str:
    path_value = arguments.get("path", ".")
    recursive = arguments.get("recursive", False)
    file_type = arguments.get("file_type")

    if not isinstance(path_value, str):
        raise ValueError("工具参数 'path' 如果提供必须是字符串。")

    if not isinstance(recursive, bool):
        raise ValueError("工具参数 'recursive' 必须是布尔值。")

    path = Path(path_value or ".")
    if not path.exists():
        return f"目录 {path} 不存在。"
    if not path.is_dir():
        return f"路径 {path} 不是目录。"

    entries = []

    if recursive:
        # 递归列出所有文件
        pattern = "**/*"
        for item in sorted(path.glob(pattern)):
            if item.is_file():
                # 过滤文件类型
                if file_type:
                    if not isinstance(file_type, str):
                        raise ValueError("file_type 必须是字符串。")
                    if not item.name.endswith(file_type):
                        continue
                # 使用相对路径
                rel_path = item.relative_to(path)
                entries.append(str(rel_path))
            elif item.is_dir():
                rel_path = item.relative_to(path)
                entries.append(str(rel_path) + "/")
    else:
        # 只列出当前目录
        for item in sorted(path.iterdir()):
            if item.is_file():
                # 过滤文件类型
                if file_type:
                    if not isinstance(file_type, str):
                        raise ValueError("file_type 必须是字符串。")
                    if not item.name.endswith(file_type):
                        continue
                entries.append(item.name)
            elif item.is_dir():
                entries.append(item.name + "/")

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


def edit_file(arguments: Dict[str, Any]) -> str:
    """在指定位置编辑文件内容（插入、替换或删除代码）。"""
    import re

    path_value = _require_str(arguments, "path")
    operation = _require_str(arguments, "operation")

    if operation not in ["insert", "replace", "delete"]:
        raise ValueError("operation 必须是 'insert'、'replace' 或 'delete' 之一。")

    path = Path(path_value)
    if not path.exists():
        return f"文件 {path} 不存在。"
    if not path.is_file():
        return f"路径 {path} 不是文件。"

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    line_start = arguments.get("line_start")

    if not isinstance(line_start, int) or line_start < 1:
        raise ValueError("line_start 必须是大于 0 的整数。")

    # 转换为 0 索引
    start_idx = line_start - 1

    if operation == "insert":
        content = arguments.get("content", "")
        if not isinstance(content, str):
            raise ValueError("content 必须是字符串。")

        # 确保内容以换行符结尾
        if content and not content.endswith("\n"):
            content += "\n"

        if start_idx > len(lines):
            return f"行号 {line_start} 超出文件范围（共 {len(lines)} 行）。"

        lines.insert(start_idx, content)
        path.write_text("".join(lines), encoding="utf-8")
        return f"已在 {path} 的第 {line_start} 行插入 {len(content)} 个字符。"

    elif operation in ["replace", "delete"]:
        line_end = arguments.get("line_end")
        if not isinstance(line_end, int) or line_end < line_start:
            raise ValueError("line_end 必须是大于等于 line_start 的整数。")

        end_idx = line_end  # 删除到 line_end（包含）

        if start_idx >= len(lines) or end_idx > len(lines):
            return f"行号范围 {line_start}-{line_end} 超出文件范围（共 {len(lines)} 行）。"

        if operation == "replace":
            content = arguments.get("content", "")
            if not isinstance(content, str):
                raise ValueError("content 必须是字符串。")

            if content and not content.endswith("\n"):
                content += "\n"

            lines[start_idx:end_idx] = [content]
            path.write_text("".join(lines), encoding="utf-8")
            return f"已替换 {path} 的第 {line_start}-{line_end} 行。"

        else:  # delete
            del lines[start_idx:end_idx]
            path.write_text("".join(lines), encoding="utf-8")
            return f"已删除 {path} 的第 {line_start}-{line_end} 行。"


def search_in_file(arguments: Dict[str, Any]) -> str:
    """在文件中搜索文本或正则表达式模式。"""
    import re

    path_value = _require_str(arguments, "path")
    pattern = _require_str(arguments, "pattern")
    context_lines = arguments.get("context_lines", 2)

    if not isinstance(context_lines, int) or context_lines < 0:
        raise ValueError("context_lines 必须是非负整数。")

    path = Path(path_value)
    if not path.exists():
        return f"文件 {path} 不存在。"
    if not path.is_file():
        return f"路径 {path} 不是文件。"

    lines = path.read_text(encoding="utf-8").splitlines()

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"正则表达式错误：{e}"

    matches = []
    for line_num, line in enumerate(lines, start=1):
        if regex.search(line):
            # 获取上下文
            start = max(0, line_num - 1 - context_lines)
            end = min(len(lines), line_num + context_lines)

            context = []
            for i in range(start, end):
                prefix = ">>> " if i == line_num - 1 else "    "
                context.append(f"{prefix}{i + 1}: {lines[i]}")

            matches.append("\n".join(context))

    if not matches:
        return f"在 {path} 中未找到匹配 '{pattern}' 的内容。"

    return f"在 {path} 中找到 {len(matches)} 处匹配：\n\n" + "\n\n".join(matches)


def run_tests(arguments: Dict[str, Any]) -> str:
    """运行 Python 测试套件（支持 pytest 和 unittest）。"""
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
    """运行代码检查工具（支持 pylint、flake8、mypy、black）。"""
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
