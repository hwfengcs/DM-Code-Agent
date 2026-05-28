"""LLM 驱动的 ReAct 智能体的 CLI 入口点。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from dm_agent import (
    LLMError,
    ReactAgent,
    Tool,
    create_llm_client,
    default_tools,
    PROVIDER_DEFAULTS,
)
from dm_agent.mcp import MCPManager, load_mcp_config
from dm_agent.skills import SkillManager
from dm_agent.tracing import TraceWriter

# 尝试导入 colorama 用于彩色输出
try:
    from colorama import Fore, Style, init as colorama_init

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


@dataclass
class Config:
    """运行时配置"""

    api_key: str
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    max_steps: int = 100
    temperature: float = 0.7
    show_steps: bool = False


# 配置文件路径
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")


class UI:
    """Small terminal UI layer built on colorama, with no optional dependencies."""

    WIDTH = 88

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
        width = UI.width()
        if label:
            prefix = f" {label} "
            line = prefix + "-" * max(width - len(prefix), 0)
        else:
            line = "-" * width
        print(UI.paint(line, color, dim=not label))

    @staticmethod
    def banner(title: str, subtitle: str = "") -> None:
        print()
        UI.rule()
        print(UI.paint(title, Fore.GREEN, bright=True))
        if subtitle:
            print(UI.paint(subtitle, Fore.WHITE, dim=True))
        UI.rule()

    @staticmethod
    def section(title: str, subtitle: str = "") -> None:
        print()
        print(UI.paint(f"-- {title}", Fore.CYAN, bright=True))
        if subtitle:
            for line in UI.wrap(subtitle, width=UI.width() - 4):
                print(UI.paint("| ", Fore.CYAN) + line)
        print(UI.paint("-" * min(UI.width(), 72), Fore.CYAN, dim=True))

    @staticmethod
    def panel(title: str, body: str = "", *, color: str = Fore.CYAN) -> None:
        print()
        print(UI.paint(f"-- {title}", color, bright=True))
        if body:
            for raw_line in str(body).splitlines() or [""]:
                wrapped = UI.wrap(raw_line, width=UI.width() - 4) or [""]
                for line in wrapped:
                    print(UI.paint("| ", color) + line)
        print(UI.paint("-" * min(UI.width(), 72), color, dim=True))

    @staticmethod
    def wrap(text: str, *, width: int | None = None) -> List[str]:
        return textwrap.wrap(
            str(text),
            width=width or UI.width() - 4,
            replace_whitespace=False,
            drop_whitespace=False,
        )

    @staticmethod
    def status(kind: str, message: str, detail: str = "") -> None:
        palette = {
            "ok": (Fore.GREEN, "OK"),
            "error": (Fore.RED, "ERR"),
            "warn": (Fore.YELLOW, "WARN"),
            "info": (Fore.CYAN, "INFO"),
            "run": (Fore.MAGENTA, "RUN"),
        }
        color, icon = palette.get(kind, palette["info"])
        line = f"{UI.paint(f'[{icon}]', color, bright=True)} {message}"
        if detail:
            line += UI.paint(f"  {detail}", Fore.WHITE, dim=True)
        print(line)

    @staticmethod
    def key_values(title: str, rows: List[tuple[str, Any]]) -> None:
        UI.section(title)
        key_width = max((len(key) for key, _ in rows), default=0)
        for key, value in rows:
            print(
                f"  {UI.paint(key.ljust(key_width), Fore.WHITE, dim=True)}  "
                f"{UI.paint(str(value), Fore.YELLOW)}"
            )

    @staticmethod
    def menu(items: List[tuple[str, str]]) -> None:
        UI.section("主菜单", "输入编号选择一个操作")
        for index, (title, description) in enumerate(items, start=1):
            badge = UI.paint(f"{index:>2}", Fore.GREEN, bright=True)
            print(f"  {badge}  {UI.paint(title, Fore.WHITE, bright=True)}")
            print(f"      {UI.paint(description, Fore.WHITE, dim=True)}")
        print()

    @staticmethod
    def truncate(value: Any, limit: int = 220) -> str:
        text = str(value)
        if len(text) <= limit:
            return text
        return text[: max(limit - 3, 0)].rstrip() + "..."


def configure_console_encoding() -> None:
    """Avoid crashes when Windows terminals cannot encode Unicode status symbols."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass


def load_config_from_file() -> Dict[str, Any]:
    """从配置文件加载设置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            UI.status("warn", "配置文件加载失败，使用默认设置", str(e))
    return {}


def save_config_to_file(config: Config) -> None:
    """保存配置到文件"""
    try:
        config_data = {
            "provider": config.provider,
            "model": config.model,
            "base_url": config.base_url,
            "max_steps": config.max_steps,
            "temperature": config.temperature,
            "show_steps": config.show_steps,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        UI.status("ok", "配置已保存")
    except Exception as e:
        UI.status("error", "配置保存失败", str(e))


def get_api_key_for_provider(provider: str) -> str | None:
    """根据提供商获取对应的 API 密钥"""
    provider_env_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "CLAUDE_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    env_var = provider_env_map.get(provider.lower())
    return os.getenv(env_var) if env_var else None


def parse_args(argv: Any) -> argparse.Namespace:
    # 先加载配置文件中的默认值
    saved_config = load_config_from_file()

    parser = argparse.ArgumentParser(description="运行基于 LLM 的 ReAct 智能体来完成任务描述。")
    parser.add_argument("task", nargs="?", help="智能体要完成的自然语言任务。")

    # 获取配置中的提供商或默认值
    default_provider = saved_config.get("provider", "deepseek")

    # 根据提供商获取对应的 API 密钥
    default_api_key = get_api_key_for_provider(default_provider)

    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=default_api_key,
        help="API 密钥（默认使用环境变量）。",
    )
    parser.add_argument(
        "--provider",
        default=saved_config.get("provider", "deepseek"),
        help="LLM 提供商 (deepseek/openai/claude/gemini，默认：deepseek)。",
    )
    parser.add_argument(
        "--model",
        default=saved_config.get("model", "deepseek-chat"),
        help="模型标识符（默认根据提供商选择）。",
    )
    parser.add_argument(
        "--base-url",
        dest="base_url",
        default=saved_config.get("base_url"),
        help="API 基础 URL（可选，使用提供商默认值）。",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=saved_config.get("max_steps", 100),
        help="放弃前的最大推理/工具步骤数（默认：100）。",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=saved_config.get("temperature", 0.7),
        help="模型的采样温度（默认：0.7）。",
    )
    parser.add_argument(
        "--show-steps",
        action="store_true",
        default=saved_config.get("show_steps", False),
        help="打印智能体执行的中间 ReAct 步骤。",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="启动交互式菜单模式。",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        help="将本次任务的结构化执行轨迹写入 JSONL 文件。",
    )
    parser.add_argument(
        "--trace-llm-io",
        action="store_true",
        help="在 trace 中包含完整 LLM 输入/输出。仅建议在私有调试时启用。",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="将本次任务的人类可读运行报告写入 Markdown 文件。",
    )
    return parser.parse_args(argv)


def print_separator(char: str = "=", length: int = 70) -> None:
    """打印分隔线"""
    _ = (char, length)
    UI.rule()


def print_header(text: str) -> None:
    """打印标题"""
    UI.banner(text)


def print_welcome() -> None:
    """打印欢迎界面"""
    UI.banner("DM-Code-Agent", "Local-first code agent with trace, tools, skills, and memory.")

    # 显示配置文件状态
    if os.path.exists(CONFIG_FILE):
        UI.status("ok", "已加载配置文件", "config.json")
    else:
        UI.status("info", "使用默认配置", "max_steps=100 | temperature=0.7")
    print()


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


def show_tools(tools: List[Tool]) -> None:
    """显示可用工具列表"""
    UI.section("可用工具", f"{len(tools)} 个工具已加载")

    for idx, tool in enumerate(tools, start=1):
        print(
            f"  {UI.paint(f'{idx:>2}', Fore.GREEN, bright=True)}  "
            f"{UI.paint(tool.name, Fore.WHITE, bright=True)}"
        )
        for line in UI.wrap(tool.description, width=UI.width() - 8):
            print(f"      {UI.paint(line, Fore.WHITE, dim=True)}")

    UI.rule()


def show_skills(skill_manager: SkillManager) -> None:
    """显示可用技能列表"""
    skills_info = skill_manager.get_all_skill_info()
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

    UI.rule()


def configure_settings(config: Config) -> None:
    """配置设置"""
    UI.key_values(
        "当前配置",
        [
            ("Provider", config.provider),
            ("Model", config.model),
            ("Base URL", config.base_url),
            ("Max steps", config.max_steps),
            ("Temperature", config.temperature),
            ("Show steps", "是" if config.show_steps else "否"),
        ],
    )
    UI.status("info", "选择要修改的设置", "直接回车跳过")
    print()

    config_changed = False

    # 修改提供商
    provider_input = (
        input(f"LLM 提供商 (deepseek/openai/claude/gemini) [{config.provider}]: ").strip().lower()
    )
    if provider_input and provider_input in ["deepseek", "openai", "claude", "gemini"]:
        if provider_input != config.provider:
            # 尝试获取新提供商的 API 密钥
            new_api_key = get_api_key_for_provider(provider_input)
            if not new_api_key:
                UI.status("error", f"未找到 {provider_input.upper()}_API_KEY 环境变量")
                UI.status("warn", f"请在 .env 文件中配置 {provider_input.upper()}_API_KEY")
            else:
                config.provider = provider_input
                config.api_key = new_api_key  # 更新 API 密钥
                # 自动更新默认模型和 base_url
                defaults = PROVIDER_DEFAULTS.get(provider_input, {})
                config.model = defaults.get("model", config.model)
                config.base_url = defaults.get("base_url", config.base_url)
                config_changed = True
                UI.status("ok", f"已更新提供商为 {provider_input}", "模型和 URL 已自动调整")
    elif provider_input and provider_input not in ["deepseek", "openai", "claude", "gemini"]:
        UI.status("error", "无效的提供商")

    # 修改模型
    model_input = input(f"模型名称 [{config.model}]: ").strip()
    if model_input:
        config.model = model_input
        config_changed = True
        UI.status("ok", f"已更新模型为 {model_input}")

    # 修改 Base URL
    base_url_input = input(f"Base URL [{config.base_url}]: ").strip()
    if base_url_input:
        config.base_url = base_url_input
        config_changed = True
        UI.status("ok", f"已更新 Base URL 为 {base_url_input}")

    # 修改最大步骤数
    try:
        max_steps_input = input(f"最大步骤数 [{config.max_steps}]: ").strip()
        if max_steps_input:
            new_max_steps = int(max_steps_input)
            if new_max_steps > 0:
                config.max_steps = new_max_steps
                config_changed = True
                UI.status("ok", f"已更新最大步骤数为 {new_max_steps}")
            else:
                UI.status("error", "最大步骤数必须大于 0")
    except ValueError:
        UI.status("error", "无效的数字")

    # 修改温度
    try:
        temp_input = input(f"温度 (0.0-2.0) [{config.temperature}]: ").strip()
        if temp_input:
            new_temp = float(temp_input)
            if 0.0 <= new_temp <= 2.0:
                config.temperature = new_temp
                config_changed = True
                UI.status("ok", f"已更新温度为 {new_temp}")
            else:
                UI.status("error", "温度必须在 0.0 到 2.0 之间")
    except ValueError:
        UI.status("error", "无效的数字")

    # 修改显示步骤
    show_steps_input = (
        input(f"显示步骤 (y/n) [{'y' if config.show_steps else 'n'}]: ").strip().lower()
    )
    if show_steps_input in ["y", "yes", "是"]:
        if not config.show_steps:
            config.show_steps = True
            config_changed = True
        UI.status("ok", "已启用显示步骤")
    elif show_steps_input in ["n", "no", "否"]:
        if config.show_steps:
            config.show_steps = False
            config_changed = True
        UI.status("ok", "已禁用显示步骤")

    # 保存配置
    if config_changed:
        print()
        save_choice = (
            input(f"{Fore.CYAN}是否保存为永久配置？(y/n) [y]: {Style.RESET_ALL}").strip().lower()
        )
        if save_choice in ["", "y", "yes", "是"]:
            save_config_to_file(config)

    print_separator("-")


def display_result(result: Dict[str, Any], show_steps: bool = False) -> None:
    """格式化显示任务结果"""
    if show_steps and result.get("steps"):
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


def collect_git_status() -> List[str]:
    """Return short git status lines for the current workspace, if available."""
    try:
        completed = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def write_run_report(
    path: Path,
    *,
    config: Config,
    task: str,
    result: Dict[str, Any],
    trace_path: Path | None = None,
    git_status_before: List[str] | None = None,
    git_status_after: List[str] | None = None,
) -> None:
    """Write a human-readable Markdown report for one agent run."""
    metadata = result.get("metadata", {})
    steps = result.get("steps", [])
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# DM-Code-Agent Run Report",
        "",
        "## Task",
        "",
        task,
        "",
        "## Runtime",
        "",
        f"- Provider: `{config.provider}`",
        f"- Model: `{config.model}`",
        f"- Status: `{metadata.get('status', 'unknown')}`",
        f"- Duration: `{float(metadata.get('duration_seconds', 0.0)):.2f}s`",
        f"- Steps: `{len(steps)}`",
        f"- Tool errors: `{metadata.get('tool_error_count', 0)}`",
        f"- Replans: `{metadata.get('replan_count', 0)}`",
    ]
    if trace_path:
        lines.append(f"- Trace: `{trace_path}`")

    before = git_status_before or []
    after = git_status_after or []
    lines.extend(["", "## Workspace Status", ""])
    if not before and not after:
        lines.append("No git status information available.")
    else:
        lines.append(f"- Dirty entries before run: `{len(before)}`")
        lines.append(f"- Dirty entries after run: `{len(after)}`")
        if before:
            lines.extend(["", "Before:", ""])
            lines.extend(f"- `{line}`" for line in before)
        if after:
            lines.extend(["", "After:", ""])
            lines.extend(f"- `{line}`" for line in after)

    lines.extend(
        [
            "",
            "## Steps",
            "",
            "| # | Action | Observation |",
            "| ---: | --- | --- |",
        ]
    )
    for index, step in enumerate(steps, start=1):
        observation = str(step.get("observation", "")).replace("\n", " ")
        if len(observation) > 180:
            observation = observation[:177] + "..."
        lines.append(f"| {index} | `{step.get('action', '')}` | {observation} |")

    lines.extend(
        [
            "",
            "## Final Answer",
            "",
            str(result.get("final_answer", "")),
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


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
            action = UI.paint(step.action, Fore.WHITE, bright=True)
            print(f"  {UI.paint(f'{step_num:>2}', Fore.CYAN)}  {action}", end=" ")
            if step.action_input:
                print(UI.paint("with input", Fore.WHITE, dim=True), end=" ")
            UI.status(status, "done" if status == "ok" else "failed")

    return callback


def multi_turn_conversation(
    config: Config, tools: List[Tool], skill_manager: SkillManager | None = None
) -> None:
    """多轮对话模式"""
    UI.section(
        "多轮对话",
        "同一个 agent 实例会保留当前会话，并使用本地原子记忆整理旧上下文。"
        "输入 exit 退出，输入 reset 重置。",
    )

    try:
        # 创建客户端和智能体
        client = create_llm_client(
            provider=config.provider,
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
        )
        step_callback = create_step_callback(config.show_steps)

        agent = ReactAgent(
            client,
            tools,
            max_steps=config.max_steps,
            temperature=config.temperature,
            step_callback=step_callback,
            skill_manager=skill_manager,
        )

        conversation_count = 0

        while True:
            UI.section(f"对话 {conversation_count + 1}")
            task = input(
                f"{UI.paint('请输入任务', Fore.YELLOW)} "
                f"{UI.paint('(exit 退出，reset 重置历史)', Fore.WHITE, dim=True)}\n> "
            ).strip()

            if not task:
                UI.status("error", "任务描述不能为空")
                continue

            if task.lower() == "exit":
                UI.status("info", "退出多轮对话模式")
                break

            if task.lower() == "reset":
                agent.reset_conversation()
                conversation_count = 0
                UI.status("ok", "对话历史已重置")
                continue

            try:
                UI.status("run", "正在执行任务")

                # 执行任务
                result = agent.run(task)
                conversation_count += 1

                # 显示最终结果
                display_result(result, show_steps=False)

            except LLMError as e:
                UI.status("error", "API 错误", str(e))
            except KeyboardInterrupt:
                UI.status("info", "退出多轮对话模式")
                break
            except Exception as e:
                UI.status("error", "发生错误", str(e))

    except Exception as e:
        UI.status("error", "初始化错误", str(e))


def execute_task(
    config: Config, tools: List[Tool], skill_manager: SkillManager | None = None
) -> None:
    """执行任务"""
    UI.section("执行新任务")
    print(UI.paint("请输入任务描述（输入完成后按回车）：", Fore.YELLOW))

    task = input("> ").strip()

    if not task:
        UI.status("error", "任务描述不能为空")
        return

    try:
        # 创建客户端和智能体
        client = create_llm_client(
            provider=config.provider,
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
        )

        # 创建步骤回调函数
        step_callback = create_step_callback(config.show_steps)

        agent = ReactAgent(
            client,
            tools,
            max_steps=config.max_steps,
            temperature=config.temperature,
            step_callback=step_callback,
            skill_manager=skill_manager,
        )

        UI.status("run", "正在执行任务")

        # 执行任务
        result = agent.run(task)

        # 显示最终结果
        display_result(result, show_steps=False)

    except LLMError as e:
        UI.status("error", "API 错误", str(e))
    except KeyboardInterrupt:
        UI.status("warn", "任务已被用户中断")
    except Exception as e:
        UI.status("error", "发生错误", str(e))


def interactive_mode(config: Config) -> int:
    """交互式菜单模式"""
    print_welcome()

    # 初始化 MCP 管理器
    mcp_config = load_mcp_config()
    mcp_manager = MCPManager(mcp_config)

    # 启动所有启用的 MCP 服务器
    UI.status("run", "正在加载 MCP 服务器")
    started_count = mcp_manager.start_all()
    if started_count > 0:
        UI.status("ok", f"成功启动 {started_count} 个 MCP 服务器")
    else:
        UI.status("info", "未启用 MCP 服务器")

    # 获取包含 MCP 工具的工具列表
    mcp_tools = mcp_manager.get_tools()
    tools = default_tools(include_mcp=True, mcp_tools=mcp_tools)

    if mcp_tools:
        UI.status("ok", f"加载了 {len(mcp_tools)} 个 MCP 工具")

    # 初始化技能管理器
    skill_manager = SkillManager()
    skill_count = skill_manager.load_all()
    if skill_count > 0:
        UI.status("ok", f"加载了 {skill_count} 个技能")
    else:
        UI.status("info", "未加载任何技能")

    try:
        while True:
            try:
                print_menu()
                choice = input(f"{UI.paint('选择操作', Fore.CYAN)} (1-6): ").strip()

                if choice == "1":
                    # 执行新任务
                    execute_task(config, tools, skill_manager)

                elif choice == "2":
                    # 多轮对话模式
                    multi_turn_conversation(config, tools, skill_manager)

                elif choice == "3":
                    # 查看工具列表
                    show_tools(tools)

                elif choice == "4":
                    # 配置设置
                    configure_settings(config)

                elif choice == "5":
                    # 查看技能列表
                    show_skills(skill_manager)

                elif choice == "6":
                    # 退出程序
                    UI.status("info", "感谢使用，再见")
                    return 0

                else:
                    UI.status("error", "无效的选择", "请输入 1-6")

            except KeyboardInterrupt:
                UI.status("info", "感谢使用，再见")
                return 0
            except EOFError:
                UI.status("info", "感谢使用，再见")
                return 0
            except Exception as e:
                UI.status("error", "发生错误", str(e))

    finally:
        # 清理 MCP 资源
        UI.status("run", "正在关闭 MCP 服务器")
        mcp_manager.stop_all()
        UI.status("ok", "MCP 服务器已关闭")


def run_single_task(
    config: Config,
    task: str,
    *,
    trace_path: Path | None = None,
    trace_llm_io: bool = False,
    report_path: Path | None = None,
) -> int:
    """运行单个任务（命令行模式）"""
    # 初始化 MCP
    mcp_config = load_mcp_config()
    mcp_manager = MCPManager(mcp_config)
    trace_writer: TraceWriter | None = None

    try:
        # 启动 MCP 服务器
        started_count = mcp_manager.start_all()
        if started_count > 0:
            UI.status("ok", f"启动了 {started_count} 个 MCP 服务器")

        # 获取工具
        mcp_tools = mcp_manager.get_tools()
        tools = default_tools(include_mcp=True, mcp_tools=mcp_tools)

        # 初始化技能管理器
        skill_manager = SkillManager()
        skill_count = skill_manager.load_all()

        client = create_llm_client(
            provider=config.provider,
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
        )
        if trace_path:
            trace_writer = TraceWriter(trace_path, capture_llm_io=trace_llm_io)
            trace_writer.record(
                "runtime",
                {
                    "provider": config.provider,
                    "model": config.model,
                    "base_url": config.base_url,
                    "max_steps": config.max_steps,
                    "temperature": config.temperature,
                    "show_steps": config.show_steps,
                    "mcp_started_count": started_count,
                    "mcp_tool_count": len(mcp_tools),
                    "skill_count": skill_count,
                    "trace_llm_io": trace_llm_io,
                },
            )

        # 创建步骤回调函数
        step_callback = create_step_callback(config.show_steps)

        agent = ReactAgent(
            client,
            tools,
            max_steps=config.max_steps,
            temperature=config.temperature,
            step_callback=step_callback,
            skill_manager=skill_manager,
            trace_writer=trace_writer,
        )

        UI.panel(
            "Run",
            (
                f"task       {task}\n"
                f"provider   {config.provider}\n"
                f"model      {config.model}\n"
                f"max steps  {config.max_steps}"
            ),
            color=Fore.CYAN,
        )

        git_status_before = collect_git_status()
        result = agent.run(task)
        git_status_after = collect_git_status()
        if report_path:
            write_run_report(
                report_path,
                config=config,
                task=task,
                result=result,
                trace_path=trace_path,
                git_status_before=git_status_before,
                git_status_after=git_status_after,
            )

        # 显示最终结果
        display_result(result, show_steps=False)
        if trace_writer:
            UI.status("ok", "Trace 已写入", str(trace_writer.path))
        if report_path:
            UI.status("ok", "Report 已写入", str(report_path))

        return 0

    except LLMError as e:
        if trace_writer:
            trace_writer.record("run_error", {"error_type": "LLMError", "message": str(e)})
        print(f"{UI.paint('[ERR] API 错误', Fore.RED, bright=True)} {e}", file=sys.stderr)
        return 1
    except Exception as e:
        if trace_writer:
            trace_writer.record(
                "run_error",
                {"error_type": type(e).__name__, "message": str(e)},
            )
        print(f"{UI.paint('[ERR] 发生错误', Fore.RED, bright=True)} {e}", file=sys.stderr)
        return 1
    finally:
        if trace_writer:
            trace_writer.close()
        # 清理 MCP 资源
        mcp_manager.stop_all()


def main(argv: Any = None) -> int:
    """主入口函数"""
    configure_console_encoding()
    load_dotenv()
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # 如果没有提供 API 密钥，尝试根据提供商获取
    if not args.api_key:
        args.api_key = get_api_key_for_provider(args.provider)

    # 检查 API 密钥
    if not args.api_key:
        print(UI.paint("[ERR] 缺少 API 密钥", Fore.RED, bright=True), file=sys.stderr)
        print(f"请提供 --api-key 或设置环境变量 {args.provider.upper()}_API_KEY。", file=sys.stderr)
        return 2

    # 获取提供商的默认配置
    provider_defaults = PROVIDER_DEFAULTS.get(args.provider, {})

    # 如果没有指定 base_url，使用提供商默认值
    if not args.base_url:
        args.base_url = provider_defaults.get("base_url", "https://api.deepseek.com")

    # 如果模型是默认的 deepseek-chat 但提供商不是 deepseek，更新模型
    if args.model == "deepseek-chat" and args.provider != "deepseek":
        args.model = provider_defaults.get("model", args.model)

    # 创建配置
    config = Config(
        api_key=args.api_key,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        max_steps=args.max_steps,
        temperature=args.temperature,
        show_steps=args.show_steps,
    )

    # 如果提供了任务参数，直接执行任务
    if args.task:
        return run_single_task(
            config,
            args.task,
            trace_path=args.trace,
            trace_llm_io=args.trace_llm_io,
            report_path=args.report,
        )

    # 如果指定了交互模式或没有提供任务，进入交互式菜单
    if args.interactive or not args.task:
        return interactive_mode(config)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
