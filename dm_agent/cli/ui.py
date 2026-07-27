"""终端渲染层：Rich 优先、colorama 兜底的展示原语与只读界面。

本模块是 CLI 的最底层，不依赖 dm_agent.cli 内的任何其他模块，也不认识 Config。
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any, ClassVar

from dm_agent.skills import SkillManager
from dm_agent.tools import Tool

try:
    from rich import box
    from rich.console import Console, Group
    from rich.padding import Padding
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
    RICH_CONSOLE = Console(highlight=False, soft_wrap=True)
except ImportError:
    RICH_AVAILABLE = False
    RICH_CONSOLE = None

# 尝试导入 colorama 用于彩色输出
try:
    from colorama import Fore, Style
    from colorama import init as colorama_init

    colorama_init(autoreset=True)
    COLORS_AVAILABLE = True
except ImportError:
    COLORS_AVAILABLE = False

    # 如果没有 colorama，定义空的颜色常量
    class Fore:
        GREEN = ""
        YELLOW = ""
        RED = ""
        CYAN = ""
        MAGENTA = ""
        BLUE = ""
        WHITE = ""

    class Style:
        BRIGHT = ""
        DIM = ""
        RESET_ALL = ""


class UI:
    """Terminal UI layer with Rich rendering and a colorama fallback."""

    WIDTH = 88
    RICH_STYLES: ClassVar[dict[str, str]] = {
        "ok": "bold white on green",
        "error": "bold white on red",
        "warn": "bold black on yellow",
        "info": "bold white on blue",
        "run": "bold white on magenta",
    }
    RICH_LABELS: ClassVar[dict[str, str]] = {
        "ok": "DONE",
        "error": "ERROR",
        "warn": "WARN",
        "info": "INFO",
        "run": "RUN",
    }

    @staticmethod
    def rich_enabled() -> bool:
        return RICH_AVAILABLE and RICH_CONSOLE is not None

    @staticmethod
    def clear() -> None:
        if UI.rich_enabled():
            RICH_CONSOLE.clear()
            return
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def width() -> int:
        return max(72, min(UI.WIDTH, shutil.get_terminal_size((UI.WIDTH, 20)).columns))

    @staticmethod
    def paint(text: str, color: str = "", *, bright: bool = False, dim: bool = False) -> str:
        style = ""
        if bright:
            style += Style.BRIGHT
        if dim:
            style += getattr(Style, "DIM", "")
        return f"{style}{color}{text}{Style.RESET_ALL}"

    @staticmethod
    def rule(label: str = "", *, color: str = Fore.CYAN) -> None:
        if UI.rich_enabled():
            title = Text(f" {label} ", style="bright_black") if label else ""
            RICH_CONSOLE.rule(title, style="bright_black")
            return
        width = UI.width()
        if label:
            prefix = f" {label} "
            line = prefix + "-" * max(width - len(prefix), 0)
        else:
            line = "-" * width
        print(UI.paint(line, color, dim=not label))

    @staticmethod
    def banner(title: str, subtitle: str = "") -> None:
        if UI.rich_enabled():
            heading = Text()
            if title == "DM-Code-Agent":
                heading.append("DM", style="bold cyan")
                heading.append("-Code-Agent", style="bold white")
            else:
                heading.append(title, style="bold white")

            body: Group | Text
            if subtitle:
                caption = Text(subtitle, style="bright_black")
                body = Group(heading, Text(""), caption)
            else:
                body = heading
            RICH_CONSOLE.print(
                Panel(
                    body,
                    border_style="bright_black",
                    box=box.ROUNDED,
                    padding=(1, 2),
                    expand=True,
                    subtitle=(
                        Text("trace  tools  skills  memory", style="bright_black")
                        if title == "DM-Code-Agent"
                        else None
                    ),
                )
            )
            return
        print()
        print(UI.paint(title, Fore.GREEN, bright=True))
        if subtitle:
            print("  " + UI.paint(subtitle, Fore.WHITE, dim=True))
        print()

    @staticmethod
    def section(title: str, subtitle: str = "") -> None:
        if UI.rich_enabled():
            text = Text()
            text.append(title, style="bold white")
            if subtitle:
                text.append("\n")
                text.append(subtitle, style="bright_black")
            RICH_CONSOLE.print(Padding(text, (1, 0, 0, 0)))
            return
        print()
        print(UI.paint(title, Fore.CYAN, bright=True))
        if subtitle:
            for line in UI.wrap(subtitle, width=UI.width() - 4):
                print("  " + UI.paint(line, Fore.WHITE, dim=True))

    @staticmethod
    def panel(title: str, body: str = "", *, color: str = Fore.CYAN) -> None:
        if UI.rich_enabled():
            style = UI._rich_color(color)
            RICH_CONSOLE.print(
                Panel(
                    UI._rich_wrapped_text(str(body), width=UI.width() - 10),
                    title=Text(f" {title} ", style=f"bold {style}"),
                    title_align="left",
                    border_style="bright_black",
                    box=box.ROUNDED,
                    padding=(1, 2),
                    expand=True,
                )
            )
            return
        print()
        print(UI.paint(title, color, bright=True))
        if body:
            for raw_line in str(body).splitlines() or [""]:
                wrapped = UI.wrap(raw_line, width=UI.width() - 4) or [""]
                for line in wrapped:
                    print("  " + line)

    @staticmethod
    def wrap(text: str, *, width: int | None = None) -> list[str]:
        return textwrap.wrap(
            str(text),
            width=width or UI.width() - 4,
            replace_whitespace=False,
            drop_whitespace=False,
        )

    @staticmethod
    def _rich_wrapped_text(text: str, *, width: int) -> Text:
        wrapped = Text()
        target_width = max(36, width)
        lines: list[str] = []
        for raw_line in str(text).splitlines() or [""]:
            if raw_line.strip():
                lines.extend(UI.wrap(raw_line, width=target_width) or [""])
            else:
                lines.append("")
        for index, line in enumerate(lines):
            if index:
                wrapped.append("\n")
            wrapped.append(line)
        return wrapped

    @staticmethod
    def status(kind: str, message: str, detail: str = "") -> None:
        if UI.rich_enabled():
            style = UI.RICH_STYLES.get(kind, UI.RICH_STYLES["info"])
            label = UI.RICH_LABELS.get(kind, kind.upper())
            text = Text()
            text.append(f" {label:<5} ", style=style)
            text.append(" ")
            text.append(message, style="white")
            if detail:
                text.append("  ")
                text.append(detail, style="bright_black")
            RICH_CONSOLE.print(Padding(text, (0, 0, 0, 1)))
            return
        palette = {
            "ok": (Fore.GREEN, "ok"),
            "error": (Fore.RED, "err"),
            "warn": (Fore.YELLOW, "warn"),
            "info": (Fore.CYAN, "info"),
            "run": (Fore.MAGENTA, "run"),
        }
        color, icon = palette.get(kind, palette["info"])
        line = f"{UI.paint(icon.ljust(5), color, bright=True)} {message}"
        if detail:
            line += UI.paint(f"  {detail}", Fore.WHITE, dim=True)
        print(line)

    @staticmethod
    def key_values(title: str, rows: list[tuple[str, Any]]) -> None:
        if UI.rich_enabled():
            table = Table.grid(padding=(0, 3))
            table.add_column(style="bright_black", no_wrap=True)
            table.add_column(style="bold white")
            for key, value in rows:
                table.add_row(str(key), str(value))
            RICH_CONSOLE.print(
                Panel(
                    table,
                    title=Text(f" {title} ", style="bold cyan"),
                    title_align="left",
                    border_style="bright_black",
                    box=box.ROUNDED,
                    padding=(1, 2),
                )
            )
            return
        UI.section(title)
        key_width = max((len(key) for key, _ in rows), default=0)
        for key, value in rows:
            print(
                f"  {UI.paint(key.ljust(key_width), Fore.WHITE, dim=True)}  "
                f"{UI.paint(str(value), Fore.YELLOW)}"
            )

    @staticmethod
    def menu(items: list[tuple[str, str]]) -> None:
        if UI.rich_enabled():
            table = Table.grid(expand=True, padding=(0, 2))
            table.add_column(justify="right", no_wrap=True, width=5)
            table.add_column(style="bold white", no_wrap=True, width=18)
            table.add_column(style="bright_black", ratio=1)
            for index, (title, description) in enumerate(items, start=1):
                badge = Text(f" {index} ", style="bold black on cyan")
                table.add_row(badge, title, description)
            RICH_CONSOLE.print(
                Panel(
                    table,
                    title=Text(" 主菜单 ", style="bold white"),
                    title_align="left",
                    subtitle=Text("输入编号选择操作", style="bright_black"),
                    border_style="bright_black",
                    box=box.ROUNDED,
                    padding=(1, 2),
                )
            )
            return
        UI.section("主菜单", "输入编号选择一个操作")
        for index, (title, description) in enumerate(items, start=1):
            badge = UI.paint(f"[{index}]", Fore.GREEN, bright=True)
            name = UI.paint(title.ljust(14), Fore.WHITE, bright=True)
            print(f"  {badge} {name} {UI.paint(description, Fore.WHITE, dim=True)}")
        print()

    @staticmethod
    def truncate(value: Any, limit: int = 220) -> str:
        text = str(value)
        if len(text) <= limit:
            return text
        return text[: max(limit - 3, 0)].rstrip() + "..."

    @staticmethod
    def ask(
        prompt: str,
        *,
        choices: list[str] | None = None,
        default: str | None = None,
        show_choices: bool = True,
    ) -> str:
        if UI.rich_enabled():
            # 显式标注为异构 dict：默认推断会把值类型收窄成三个分支的联合，
            # 导致后面按需塞入 default 以及 ** 展开进 Prompt.ask 全部误报 arg-type。
            prompt_kwargs: dict[str, Any] = {
                "choices": choices,
                "console": RICH_CONSOLE,
                "show_choices": show_choices,
            }
            if default is not None:
                prompt_kwargs["default"] = default
            return Prompt.ask(Text(prompt, style="bold cyan"), **prompt_kwargs)
        suffix = f" [{default}]" if default is not None else ""
        return input(f"{UI.paint(prompt, Fore.CYAN)}{suffix}: ")

    @staticmethod
    def prompt_line(prompt: str, *, default: str = "") -> str:
        if UI.rich_enabled():
            return Prompt.ask(
                Text(prompt, style="bold cyan"),
                console=RICH_CONSOLE,
                default=default,
                show_default=False,
            )
        suffix = f" [{default}]" if default else ""
        return input(f"{UI.paint(prompt, Fore.CYAN)}{suffix}: ")

    @staticmethod
    def pause(prompt: str = "按 Enter 返回") -> None:
        UI.prompt_line(prompt, default="")

    @staticmethod
    def _rich_color(color: str) -> str:
        if color == Fore.GREEN:
            return "green"
        if color == Fore.YELLOW:
            return "yellow"
        if color == Fore.RED:
            return "red"
        if color == Fore.MAGENTA:
            return "magenta"
        if color == Fore.BLUE:
            return "blue"
        return "cyan"


def configure_console_encoding() -> None:
    """Avoid crashes when Windows terminals cannot encode Unicode status symbols."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            with contextlib.suppress(Exception):
                stream.reconfigure(errors="replace")


def print_separator(char: str = "=", length: int = 70) -> None:
    """打印分隔线"""
    _ = (char, length)
    UI.rule()


def print_header(text: str) -> None:
    """打印标题"""
    UI.banner(text)


def print_menu() -> None:
    """打印主菜单"""
    UI.menu(
        [
            ("执行新任务", "一次性运行一个代码维护任务"),
            ("多轮对话模式", "复用当前 agent 的短期上下文和本地记忆"),
            ("查看工具列表", "浏览文件、Shell、测试、MCP 等可用工具"),
            ("配置设置", "切换模型、温度、最大步骤和显示选项"),
            ("查看可用技能列表", "查看内置和自定义技能"),
            ("退出程序", "关闭 MCP 并返回终端"),
        ]
    )


def show_tools(tools: list[Tool]) -> None:
    """显示可用工具列表"""
    if UI.rich_enabled():
        table = Table(
            show_header=True,
            header_style="bold white",
            box=box.SIMPLE_HEAD,
            border_style="bright_black",
            pad_edge=False,
        )
        table.add_column("#", justify="right", style="cyan", no_wrap=True)
        table.add_column("Tool", style="bold white", no_wrap=True)
        table.add_column("Description", style="bright_black")
        for idx, tool in enumerate(tools, start=1):
            table.add_row(str(idx), tool.name, tool.description)
        RICH_CONSOLE.print(
            Panel(
                table,
                title=Text(f" 可用工具 ({len(tools)}) ", style="bold cyan"),
                title_align="left",
                border_style="bright_black",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        return

    UI.section("可用工具", f"{len(tools)} 个工具已加载")

    for idx, tool in enumerate(tools, start=1):
        print(
            f"  {UI.paint(f'{idx:>2}', Fore.GREEN, bright=True)}  "
            f"{UI.paint(tool.name, Fore.WHITE, bright=True)}"
        )
        for line in UI.wrap(tool.description, width=UI.width() - 8):
            print(f"      {UI.paint(line, Fore.WHITE, dim=True)}")

    print()


def show_skills(skill_manager: SkillManager) -> None:
    """显示可用技能列表"""
    skills_info = skill_manager.get_all_skill_info()
    if UI.rich_enabled():
        table = Table(
            show_header=True,
            header_style="bold white",
            box=box.SIMPLE_HEAD,
            border_style="bright_black",
            pad_edge=False,
        )
        table.add_column("#", justify="right", style="cyan", no_wrap=True)
        table.add_column("Skill", no_wrap=True)
        table.add_column("Source", style="yellow", no_wrap=True)
        table.add_column("Tools", justify="right", style="magenta", no_wrap=True)
        table.add_column("Description", style="bright_black")
        for idx, info in enumerate(skills_info, start=1):
            source = "内置" if info["is_builtin"] else "自定义"
            skill_name = Text(str(info["display_name"]), style="bold white")
            if info["is_active"]:
                skill_name.append("  ACTIVE", style="bold green")
            table.add_row(
                str(idx),
                skill_name,
                source,
                str(info["tools_count"]),
                info["description"],
            )
        body = table if skills_info else Text("暂无可用技能", style="yellow")
        RICH_CONSOLE.print(
            Panel(
                body,
                title=Text(f" 可用技能 ({len(skills_info)}) ", style="bold cyan"),
                title_align="left",
                border_style="bright_black",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        return

    UI.section("可用技能", f"{len(skills_info)} 个技能已发现")
    if not skills_info:
        UI.status("warn", "暂无可用技能")
    else:
        for idx, info in enumerate(skills_info, start=1):
            status = UI.paint("active", Fore.GREEN, bright=True) if info["is_active"] else ""
            source = "内置" if info["is_builtin"] else "自定义"
            header = (
                f"  {UI.paint(f'{idx:>2}', Fore.GREEN, bright=True)}  "
                f"{UI.paint(info['display_name'], Fore.WHITE, bright=True)}"
            )
            print(f"{header}  {status}".rstrip())
            print(
                f"      {UI.paint(info['name'], Fore.YELLOW)} | {source} | "
                f"v{info['version']} | {info['tools_count']} tools"
            )
            for line in UI.wrap(info["description"], width=UI.width() - 8):
                print(f"      {UI.paint(line, Fore.WHITE, dim=True)}")
            print(
                f"      {UI.paint('关键词', Fore.WHITE, dim=True)}  "
                f"{', '.join(info['keywords'][:8])}"
                f"{'...' if len(info['keywords']) > 8 else ''}"
            )
            print()

    print()


def ask_bool_setting(label: str, current: bool) -> bool:
    value = UI.ask(label, choices=["y", "n"], default="y" if current else "n").strip().lower()
    if value in {"y", "yes", "是"}:
        return True
    if value in {"n", "no", "否"}:
        return False
    return current


def display_result(result: dict[str, Any], show_steps: bool = False) -> None:
    """格式化显示任务结果"""
    if show_steps and result.get("steps"):
        if UI.rich_enabled():
            table = Table(
                show_header=True,
                header_style="bold white",
                box=box.SIMPLE_HEAD,
                border_style="bright_black",
                pad_edge=False,
            )
            table.add_column("#", justify="right", style="cyan", no_wrap=True)
            table.add_column("Action", style="bold white", no_wrap=True)
            table.add_column("Thought", style="bright_black")
            table.add_column("Observation", style="bright_black")
            for idx, step in enumerate(result.get("steps", []), start=1):
                table.add_row(
                    str(idx),
                    str(step.get("action", "")),
                    UI.truncate(step.get("thought", ""), 120),
                    UI.truncate(step.get("observation", ""), 140),
                )
            RICH_CONSOLE.print(
                Panel(
                    table,
                    title=Text(" 执行步骤 ", style="bold magenta"),
                    title_align="left",
                    border_style="bright_black",
                    box=box.ROUNDED,
                    padding=(1, 2),
                )
            )
        else:
            UI.section("执行步骤")
            for idx, step in enumerate(result.get("steps", []), start=1):
                print(
                    f"  {UI.paint(f'{idx:>2}', Fore.MAGENTA, bright=True)}  "
                    f"{UI.paint(str(step.get('action', '')), Fore.WHITE, bright=True)}"
                )
                print(f"      {UI.paint('thought', Fore.WHITE, dim=True)}  {step.get('thought')}")
                action_input = step.get("action_input")
                if action_input:
                    print(
                        f"      {UI.paint('input', Fore.WHITE, dim=True)}    "
                        f"{json.dumps(action_input, ensure_ascii=False)}"
                    )
                print(
                    f"      {UI.paint('observe', Fore.WHITE, dim=True)}  "
                    f"{UI.truncate(step.get('observation'))}"
                )
                print()

    final_answer = result.get("final_answer", "")
    UI.panel("最终答案", str(final_answer), color=Fore.GREEN)
    completion_summary = str(result.get("metadata", {}).get("completion_summary", "")).strip()
    if completion_summary and completion_summary != str(final_answer).strip():
        UI.panel("本轮总结", completion_summary, color=Fore.CYAN)


def format_duration(seconds: Any) -> str:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "-"
    if value < 60:
        return f"{value:.1f}s"
    minutes, remainder = divmod(int(value), 60)
    return f"{minutes}m {remainder}s"


def format_run_status(status: Any) -> str:
    value = str(status or "unknown")
    labels = {
        "success": "完成",
        "running": "运行中",
        "max_steps_exceeded": "达到步骤上限",
    }
    return labels.get(value, value)


def format_step_input(value: Any, *, limit: int = 90) -> str:
    if value in (None, "", {}):
        return "-"
    try:
        text = json.dumps(value, ensure_ascii=False)
    except TypeError:
        text = str(value)
    return UI.truncate(text, limit)


def display_completion_screen(
    result: dict[str, Any],
    *,
    task: str | None = None,
    context_status: str | None = None,
    trace_path: Path | None = None,
    report_path: Path | None = None,
    clear_screen: bool = False,
    review_hint: bool = False,
) -> None:
    if clear_screen:
        UI.clear()

    metadata = result.get("metadata", {})
    steps = result.get("steps", [])
    final_answer = str(result.get("final_answer", "")).strip()
    completion_summary = str(metadata.get("completion_summary", "")).strip()
    summary = completion_summary or final_answer or "任务已结束。"

    UI.banner("任务结束", "最终总结在这里；运行过程已收纳，可按需查看。")
    UI.panel("最终总结", summary, color=Fore.GREEN)
    if final_answer and final_answer != summary:
        UI.panel("最终答案", final_answer, color=Fore.CYAN)

    rows: list[tuple[str, Any]] = [
        ("状态", format_run_status(metadata.get("status"))),
        ("步骤", len(steps)),
        ("耗时", format_duration(metadata.get("duration_seconds"))),
        ("工具错误", metadata.get("tool_error_count", 0)),
        ("重规划", metadata.get("replan_count", 0)),
    ]
    if task:
        rows.insert(0, ("任务", UI.truncate(task, 96)))
    memory_count = metadata.get("memory_items")
    if memory_count is not None:
        rows.append(("记忆", f"{memory_count} items"))
    if context_status:
        rows.append(("会话", context_status))
    if trace_path:
        rows.append(("Trace", trace_path))
    if report_path:
        rows.append(("Report", report_path))
    elif not review_hint:
        rows.append(("过程", "使用 --report 保存 Markdown，或 --trace 保存 JSONL"))
    UI.key_values("运行概览", rows)

    if review_hint:
        UI.status("info", "查看过程", "Enter 继续 | v 分页查看步骤 | s 保存 Markdown 报告")


def display_step_page(result: dict[str, Any], *, page: int, page_size: int) -> None:
    steps = result.get("steps", [])
    total = len(steps)
    page_count = max(1, (total + page_size - 1) // page_size)
    start = page * page_size
    page_steps = steps[start : start + page_size]

    UI.clear()
    UI.banner("运行过程", f"第 {page + 1}/{page_count} 页，共 {total} 步")
    if not page_steps:
        UI.status("info", "本轮没有记录到步骤")
        return

    if UI.rich_enabled():
        table = Table(
            show_header=True,
            header_style="bold white",
            box=box.SIMPLE_HEAD,
            border_style="bright_black",
            pad_edge=False,
        )
        table.add_column("#", justify="right", style="cyan", no_wrap=True, width=4)
        table.add_column("状态", no_wrap=True, width=6)
        table.add_column("动作", style="bold white", no_wrap=True, width=18)
        table.add_column("输入", style="bright_black", ratio=1, overflow="fold")
        table.add_column("观察", style="bright_black", ratio=2, overflow="fold")
        for offset, step in enumerate(page_steps, start=start + 1):
            observation = str(step.get("observation", ""))
            action = str(step.get("action", ""))
            failed = action == "error" or "failed" in observation.lower()
            status = Text("ERR", style=UI.RICH_STYLES["error"]) if failed else Text("OK", "green")
            table.add_row(
                str(offset),
                status,
                action,
                format_step_input(step.get("action_input")),
                UI.truncate(observation, 180),
            )
        RICH_CONSOLE.print(
            Panel(
                table,
                title=Text(" 步骤摘要 ", style="bold magenta"),
                title_align="left",
                border_style="bright_black",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
    else:
        UI.section("步骤摘要")
        for offset, step in enumerate(page_steps, start=start + 1):
            action = str(step.get("action", ""))
            observation = UI.truncate(step.get("observation", ""), 180)
            print(
                f"  {UI.paint(f'{offset:>3}', Fore.CYAN, bright=True)}  "
                f"{UI.paint(action, Fore.WHITE, bright=True)}"
            )
            print(
                f"       {UI.paint('input', Fore.WHITE, dim=True)}  {format_step_input(step.get('action_input'))}"
            )
            print(f"       {UI.paint('observe', Fore.WHITE, dim=True)}  {observation}")
            print()

    UI.status("info", "导航", "n 下一页 | p 上一页 | q 返回总结")


def browse_run_steps(result: dict[str, Any], *, page_size: int = 12) -> None:
    steps = result.get("steps", [])
    if not steps:
        UI.clear()
        UI.status("info", "本轮没有可查看的步骤")
        UI.pause()
        return

    page = 0
    page_count = max(1, (len(steps) + page_size - 1) // page_size)
    while True:
        display_step_page(result, page=page, page_size=page_size)
        choice = UI.prompt_line("操作", default="q").strip().lower()
        if choice in {"", "q", "quit", "back"}:
            return
        if choice in {"n", "next"}:
            page = min(page + 1, page_count - 1)
            continue
        if choice in {"p", "prev", "previous"}:
            page = max(page - 1, 0)
            continue
        UI.status("warn", "未知操作", "请输入 n、p 或 q")
        UI.pause()


def create_step_callback(show_steps: bool):
    """创建步骤回调函数，用于实时打印 agent 执行状态"""

    def callback(step_num: int, step: Any) -> None:
        if show_steps:
            UI.panel(
                f"Step {step_num:02d} | {step.action}",
                (
                    f"thought  {step.thought}\n"
                    f"input    "
                    f"{json.dumps(step.action_input, ensure_ascii=False) if step.action_input else '-'}\n"
                    f"observe  {UI.truncate(step.observation, 360)}"
                ),
                color=Fore.MAGENTA,
            )
        else:
            status = "error" if step.action == "error" else "ok"
            should_print = (
                step_num == 1
                or step_num % 10 == 0
                or status == "error"
                or step.action in {"finish", "task_complete"}
            )
            if not should_print:
                return
            if UI.rich_enabled():
                text = Text()
                text.append(f"{step_num:02d}", style="cyan")
                text.append("  ")
                if status == "error":
                    text.append(" ERR ", style=UI.RICH_STYLES["error"])
                else:
                    text.append(" OK  ", style=UI.RICH_STYLES["ok"])
                text.append(" ")
                text.append(step.action, style="bold white")
                if step.action_input:
                    text.append("  input", style="bright_black")
                RICH_CONSOLE.print(Padding(text, (0, 0, 0, 1)))
                return

            action = UI.paint(step.action, Fore.WHITE, bright=True)
            marker = UI.paint(f"{step_num:02d}", Fore.CYAN, bright=True)
            result = UI.paint(
                "err" if status == "error" else "ok", Fore.RED if status == "error" else Fore.GREEN
            )
            suffix = UI.paint(" input", Fore.WHITE, dim=True) if step.action_input else ""
            print(f"  {marker}  {result}  {action}{suffix}")

    return callback
