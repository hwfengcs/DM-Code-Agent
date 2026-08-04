"""文件操作工具"""

from __future__ import annotations

import ast
import os
import time
from pathlib import Path
from typing import Any

from .base import _require_str

# 编辑后回显的上下文行数与总行数上限。上限存在的理由：观察会进对话历史，
# 替换一大段代码时不设限会把窗口撑爆；`--max-observation-chars` 是全局兜底，
# 不该指望它来处理这里本可以精确控制的情况。
EDIT_ECHO_CONTEXT_LINES = 3
EDIT_ECHO_MAX_LINES = 40


def _atomic_write_text(path: Path, content: str) -> str:
    """原子写入：同目录临时文件 + os.replace，避免中断留下半写文件。

    Windows 上目标被占用时 os.replace 可能抛 PermissionError；小睡后重试一次，
    仍失败则回退普通写入并在返回值中注明。返回空串表示原子写成功。
    """
    tmp_path = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        try:
            os.replace(tmp_path, path)
            return ""
        except PermissionError:
            time.sleep(0.05)
            os.replace(tmp_path, path)
            return ""
    except OSError:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        path.write_text(content, encoding="utf-8")
        return " (non-atomic fallback)"


def create_file(arguments: dict[str, Any]) -> str:
    """创建或覆盖文本文件"""
    path_value = _require_str(arguments, "path")
    content = arguments.get("content", "")
    if not isinstance(content, str):
        raise ValueError("工具参数 'content' 必须是字符串。")

    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    note = _atomic_write_text(path, content)
    return f"已将 {len(content)} 个字符写入 {path}。{note}{_check_python_syntax(path, content)}".rstrip()


def read_file(arguments: dict[str, Any]) -> str:
    """读取文本文件"""
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


def list_directory(arguments: dict[str, Any]) -> str:
    """列出目录内容"""
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


def _check_python_syntax(path: Path, content: str) -> str:
    """对 .py 内容做语法检查，返回可直接拼进观察的提示（通过时为空串）。

    **只报告，不回滚。** 分步编辑的中间态可能合法地无法解析，回滚会让工具变得
    不可预测；写入已经发生这件事必须如实呈现。

    能力边界要清楚：``ast.parse`` 只抓语法崩坏（缩进、括号、冒号）。像
    「替换时连带吞掉了一行赋值」这种语法完全合法的破坏它抓不到——那类要靠
    ``_render_edit_context`` 的回显让模型自己看见。

    措辞刻意避开 ``core.observation.FAILURE_MARKERS``（失败/错误/error/不存在）：
    这是模型下一步就能自行修复的局部问题，不该触发一次完整的重规划。同理见
    ``core.guards._block_message``。
    """
    if path.suffix != ".py":
        return ""
    try:
        ast.parse(content)
    except SyntaxError as exc:
        location = f"第 {exc.lineno} 行" if exc.lineno else "未知位置"
        return f"\n[语法检查] 未通过：{location} {exc.msg}。文件已写入，请修正后再继续。"
    except ValueError:
        # 源码含空字节等 ast 拒绝解析的内容；不阻断，交给后续测试暴露。
        return ""
    return ""


def _render_edit_context(lines: list[str], start_line: int, end_line: int) -> str:
    """回显改动后的区间，带**新**行号，改动行用 > 标出。

    这是本模块最重要的一行信息：编辑前只有「已替换第 8-10 行」这样一句回执，
    模型没有任何依据判断自己有没有改错位置，实测平均要 2.2 步之后才发现
    （见 devlog 37/38）。回显把这个延迟压到 0。
    """
    if not lines:
        return "\n[编辑后] 文件为空。"
    lo = max(1, start_line - EDIT_ECHO_CONTEXT_LINES)
    hi = min(len(lines), end_line + EDIT_ECHO_CONTEXT_LINES)
    truncated = False
    if hi - lo + 1 > EDIT_ECHO_MAX_LINES:
        hi = lo + EDIT_ECHO_MAX_LINES - 1
        truncated = True

    rendered = [
        f"{'>' if start_line <= number <= end_line else ' '}{number:>5} | "
        f"{lines[number - 1].rstrip(chr(10)).rstrip(chr(13))}"
        for number in range(lo, hi + 1)
    ]
    tail = f"\n... 回显截断，仅显示前 {EDIT_ECHO_MAX_LINES} 行" if truncated else ""
    return "\n[编辑后] 第 {lo}-{hi} 行（共 {total} 行）：\n{body}{tail}".format(
        lo=lo, hi=hi, total=len(lines), body="\n".join(rendered), tail=tail
    )


def _edit_by_old_string(path: Path, arguments: dict[str, Any]) -> str:
    """按内容精确定位替换：匹配不到或匹配多处一律不动文件。

    这是对行号模式的根治。行号会随每一次编辑漂移，而 ``replace`` 执行的是
    ``lines[start:end] = [content]``——区间给宽一行就会静默吞掉相邻代码。
    按内容定位从机制上排除了这种可能：要么命中唯一一处，要么什么都不做。
    """
    old_string = arguments["old_string"]
    if not isinstance(old_string, str):
        raise ValueError("old_string 必须是字符串。")
    if not old_string:
        raise ValueError("old_string 不能为空字符串。")
    new_string = arguments.get("new_string", "")
    if not isinstance(new_string, str):
        raise ValueError("new_string 必须是字符串。")
    for conflicting in ("operation", "line_start", "line_end"):
        if arguments.get(conflicting) is not None:
            raise ValueError(
                f"old_string 模式不能与 {conflicting} 同时使用；"
                "按内容定位时行号无意义，请二选一。"
            )

    content = path.read_text(encoding="utf-8")
    occurrences = content.count(old_string)
    # 下面两条提示同样避开 FAILURE_MARKERS：换一段 old_string 重试是局部纠正，
    # 不需要惊动 planner。
    if occurrences == 0:
        return (
            f"未命中：{path} 中没有与 old_string 逐字相同的内容"
            f"（{len(old_string)} 字符）。空白与缩进必须完全一致，"
            "先用 read_file 取回原文再重试。"
        )
    if occurrences > 1:
        return (
            f"未替换：old_string 在 {path} 中出现 {occurrences} 处，无法确定改哪一处。"
            "请补充上下文让它唯一。"
        )

    updated = content.replace(old_string, new_string, 1)
    note = _atomic_write_text(path, updated)

    prefix_lines = content[: content.index(old_string)].count("\n")
    start_line = prefix_lines + 1
    new_line_count = new_string.count("\n") + 1 if new_string else 1
    end_line = start_line + new_line_count - 1
    lines = updated.splitlines(keepends=True)
    if not new_string:
        # 纯删除时没有"改动行"可标，回显删除点周围即可。
        end_line = start_line = max(1, min(start_line, len(lines)))

    return (
        f"已按内容替换 {path} 的 1 处（{len(old_string)} -> {len(new_string)} 字符）。{note}"
        f"{_render_edit_context(lines, start_line, end_line)}"
        f"{_check_python_syntax(path, updated)}"
    ).rstrip()


def edit_file(arguments: dict[str, Any]) -> str:
    """在指定位置编辑文件内容（按内容精确替换，或按行号插入/替换/删除）"""
    path_value = _require_str(arguments, "path")

    path = Path(path_value)
    if not path.exists():
        return f"文件 {path} 不存在。"
    if not path.is_file():
        return f"路径 {path} 不是文件。"

    if arguments.get("old_string") is not None or arguments.get("new_string") is not None:
        if arguments.get("old_string") is None:
            raise ValueError("提供 new_string 时必须同时提供 old_string。")
        return _edit_by_old_string(path, arguments)

    operation = _require_str(arguments, "operation")

    if operation not in ["insert", "replace", "delete"]:
        raise ValueError("operation 必须是 'insert'、'replace' 或 'delete' 之一。")

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
        updated = "".join(lines)
        _atomic_write_text(path, updated)
        inserted_lines = content.count("\n") if content else 0
        return (
            f"已在 {path} 的第 {line_start} 行插入 {len(content)} 个字符。"
            f"{_render_edit_context(lines, line_start, line_start + max(inserted_lines - 1, 0))}"
            f"{_check_python_syntax(path, updated)}"
        )

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
            updated = "".join(lines)
            _atomic_write_text(path, updated)
            replaced_lines = content.count("\n") if content else 0
            return (
                f"已替换 {path} 的第 {line_start}-{line_end} 行。"
                f"{_render_edit_context(lines, line_start, line_start + max(replaced_lines - 1, 0))}"
                f"{_check_python_syntax(path, updated)}"
            )

        else:  # delete
            del lines[start_idx:end_idx]
            updated = "".join(lines)
            _atomic_write_text(path, updated)
            anchor = max(1, min(line_start, len(lines)))
            return (
                f"已删除 {path} 的第 {line_start}-{line_end} 行。"
                f"{_render_edit_context(lines, anchor, anchor)}"
                f"{_check_python_syntax(path, updated)}"
            )

    # 函数开头的白名单校验已保证 operation 仅为三者之一，此分支运行时不可达；
    # 保留兜底是为了在未来新增 operation 却漏写分支时立即报错，而不是静默返回 None。
    raise ValueError(f"未处理的 operation: {operation}")


def search_in_file(arguments: dict[str, Any]) -> str:
    """在文件中搜索文本或正则表达式模式"""
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
