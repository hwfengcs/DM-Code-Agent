"""Agent 装配与单任务执行：把 Config 翻译成 ReactAgent 并跑完一次 run。"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dm_agent import (
    LLMError,
    ReactAgent,
    Tool,
    create_llm_client,
    default_tools,
)
from dm_agent.core.checkpoint import RunCheckpoint
from dm_agent.mcp import MCPManager, load_mcp_config
from dm_agent.skills import SkillManager
from dm_agent.tracing import SessionWriter, TraceWriter

if TYPE_CHECKING:
    from dm_agent.extensions import ExtensionRegistry

from .config import Config, format_advanced_feature_status, resolve_advanced_features
from .report import collect_git_status, default_report_path, write_run_report
from .ui import (
    UI,
    Fore,
    browse_run_steps,
    create_step_callback,
    display_completion_screen,
)


def review_completed_run(
    result: dict[str, Any],
    *,
    config: Config,
    task: str,
    trace_path: Path | None = None,
    report_path: Path | None = None,
    context_status: str | None = None,
    git_status_before: list[str] | None = None,
    git_status_after: list[str] | None = None,
    interactive: bool = True,
) -> Path | None:
    current_report_path = report_path
    while True:
        display_completion_screen(
            result,
            task=task,
            context_status=context_status,
            trace_path=trace_path,
            report_path=current_report_path,
            clear_screen=True,
            review_hint=interactive,
        )
        if not interactive:
            return current_report_path

        choice = UI.prompt_line("操作", default="").strip().lower()
        if choice in {"", "c", "continue"}:
            return current_report_path
        if choice in {"v", "view", "steps", "process", "过程"}:
            browse_run_steps(result)
            continue
        if choice in {"s", "save", "report", "保存"}:
            current_report_path = current_report_path or default_report_path(task)
            write_run_report(
                current_report_path,
                config=config,
                task=task,
                result=result,
                trace_path=trace_path,
                git_status_before=git_status_before,
                git_status_after=git_status_after,
            )
            UI.status("ok", "Report 已保存", str(current_report_path))
            UI.pause()
            continue
        UI.status("warn", "未知操作", "Enter 继续，v 查看步骤，s 保存报告")
        UI.pause()


def create_agent(
    config: Config,
    client: Any,
    tools: list[Tool],
    *,
    step_callback: Any = None,
    skill_manager: SkillManager | None = None,
    trace_writer: SessionWriter | TraceWriter | None = None,
    extension_registry: ExtensionRegistry | None = None,
) -> ReactAgent:
    """Create a ReactAgent with the CLI's default-off advanced switches."""
    advanced = resolve_advanced_features(config)
    return ReactAgent(
        client,
        tools,
        max_steps=config.max_steps,
        temperature=config.temperature,
        step_callback=step_callback,
        skill_manager=skill_manager,
        trace_writer=trace_writer,
        max_observation_chars=config.max_observation_chars,
        context_token_budget=config.context_token_budget,
        enable_edit_guard=config.enable_edit_guard,
        enable_adaptive_replanning=advanced["adaptive_replanning"],
        max_replans=config.max_replans,
        event_bus=(
            extension_registry.create_event_bus() if extension_registry is not None else None
        ),
    )


def format_agent_context_status(agent: ReactAgent) -> str:
    stats = agent.get_context_stats()
    return (
        f"history={stats['conversation_messages']} messages | "
        f"memory={stats['memory_items']} items | "
        f"compression={'on' if stats['compression_enabled'] else 'off'}"
    )


def _assemble_agent(
    config: Config,
    *,
    mcp_manager: MCPManager,
    trace_path: Path | None,
    trace_llm_io: bool,
    checkpoint_path: Path | None,
    extension_registry: ExtensionRegistry | None,
) -> tuple[ReactAgent, SessionWriter | None]:
    """把 Config 装配成一个可用的 agent（含 MCP 工具、技能、会话日志）。

    ``run_single_task`` 与 ``run_conversation_stdin`` 共用这一段。抽出来是因为两条
    入口必须装配出**完全一样**的 agent——否则「Web 控制台跑的和命令行跑的是同一件事」
    这条保证就会从子进程这一层悄悄漏掉。
    """
    started_count = mcp_manager.start_all()
    if started_count > 0:
        UI.status("ok", f"启动了 {started_count} 个 MCP 服务器")

    mcp_tools = mcp_manager.get_tools()
    tools = default_tools(
        include_mcp=True,
        mcp_tools=mcp_tools,
        extension_registry=extension_registry,
    )

    skill_manager = SkillManager(extension_registry=extension_registry)
    skill_count = skill_manager.load_all()

    client = create_llm_client(
        provider=config.provider,
        api_key=config.api_key,
        model=config.model,
        base_url=config.base_url,
        respond_retries=config.llm_max_retries,
        extension_registry=extension_registry,
    )
    advanced = resolve_advanced_features(config)

    trace_writer: SessionWriter | None = None
    if trace_path or (checkpoint_path and checkpoint_path.suffix.lower() == ".jsonl"):
        trace_sink = TraceWriter(trace_path, capture_llm_io=trace_llm_io) if trace_path else None
        trace_writer = SessionWriter(trace_sink)
        if checkpoint_path:
            trace_writer.ensure_checkpoint_sink(checkpoint_path)
        trace_writer.record(
            "runtime",
            {
                "provider": config.provider,
                "model": config.model,
                "base_url": config.base_url,
                "max_steps": config.max_steps,
                "temperature": config.temperature,
                "show_steps": config.show_steps,
                "max_observation_chars": config.max_observation_chars,
                "context_token_budget": config.context_token_budget,
                "edit_guard_enabled": config.enable_edit_guard,
                "mcp_started_count": started_count,
                "mcp_tool_count": len(mcp_tools),
                "skill_count": skill_count,
                "trace_llm_io": trace_llm_io,
                "adaptive_replanning_enabled": advanced["adaptive_replanning"],
                "max_replans": config.max_replans,
            },
        )

    step_callback = create_step_callback(config.show_steps)
    agent = create_agent(
        config,
        client,
        tools,
        step_callback=step_callback,
        skill_manager=skill_manager,
        trace_writer=trace_writer,
        extension_registry=extension_registry,
    )
    return agent, trace_writer


def run_single_task(
    config: Config,
    task: str,
    *,
    trace_path: Path | None = None,
    trace_llm_io: bool = False,
    report_path: Path | None = None,
    checkpoint_path: Path | None = None,
    resume_state: RunCheckpoint | None = None,
    extension_registry: ExtensionRegistry | None = None,
) -> int:
    """运行单个任务（命令行模式）"""
    # 初始化 MCP
    mcp_config = load_mcp_config()
    mcp_manager = MCPManager(mcp_config)
    trace_writer: SessionWriter | None = None

    try:
        agent, trace_writer = _assemble_agent(
            config,
            mcp_manager=mcp_manager,
            trace_path=trace_path,
            trace_llm_io=trace_llm_io,
            checkpoint_path=checkpoint_path,
            extension_registry=extension_registry,
        )

        UI.panel(
            "Run",
            (
                f"task       {task}\n"
                f"provider   {config.provider}\n"
                f"model      {config.model}\n"
                f"max steps  {config.max_steps}\n"
                f"advanced   {format_advanced_feature_status(config)}"
            ),
            color=Fore.CYAN,
        )

        git_status_before = collect_git_status()
        result = agent.run(task, checkpoint_path=checkpoint_path, resume_state=resume_state)
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

        review_completed_run(
            result,
            config=config,
            task=task,
            trace_path=trace_path,
            report_path=report_path,
            git_status_before=git_status_before,
            git_status_after=git_status_after,
            interactive=False,
        )

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


def _read_conversation_message(line: str) -> dict[str, Any] | None:
    """把 stdin 上的一行解析成一条控制消息；空行与坏行返回 None。

    用 JSON 对象而不是裸文本行：任务描述里完全可能有换行。
    """
    text = line.strip()
    if not text:
        return None
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None


def run_conversation_stdin(
    config: Config,
    *,
    trace_path: Path,
    trace_llm_io: bool = False,
    extension_registry: ExtensionRegistry | None = None,
) -> int:
    """长驻会话模式：一个进程、一个 agent、顺序跑多轮。

    这是 Web 控制台多轮对话的执行端。协议刻意做成**单向**的：

    * 调用方 → 子进程：stdin 上每行一个 JSON 对象，``{"task": "..."}`` 跑一轮，
      ``{"type": "reset"}`` 清空对话历史与本地记忆。EOF 表示会话结束。
    * 子进程 → 调用方：**没有 stdout 协议**。每一轮的进展、结果、失败全都在
      ``--trace`` 的会话日志里（``run_start`` / ``run_end`` 本来就在），调用方跟读
      那个文件即可。stdout/stderr 保持人类可读日志的原样。

    这么设计有两个好处：不需要发明第二套协议，也不会被 agent 自己的打印污染；
    而且「实时看到的」与「事后审计到的」仍然是同一份字节。

    多轮共享上下文靠的是**同一个 ``ReactAgent`` 实例**——``_run_once`` 会把上一轮
    留在 ``conversation_history`` 里的消息通过 ``_adopt_existing_history(kind="carried")``
    补记进会话日志，本地记忆与折叠状态也随实例延续。这正是交互式多轮模式的做法。
    """
    # stdin 默认按平台 locale 解码（Windows 上是 GBK），中文任务会在这里被打成乱码。
    if hasattr(sys.stdin, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")

    mcp_config = load_mcp_config()
    mcp_manager = MCPManager(mcp_config)
    trace_writer: SessionWriter | None = None

    try:
        agent, trace_writer = _assemble_agent(
            config,
            mcp_manager=mcp_manager,
            trace_path=trace_path,
            trace_llm_io=trace_llm_io,
            checkpoint_path=None,
            extension_registry=extension_registry,
        )
    except Exception as e:
        if trace_writer:
            trace_writer.record(
                "run_error",
                {"error_type": type(e).__name__, "message": str(e)},
            )
            trace_writer.close()
        mcp_manager.stop_all()
        print(f"{UI.paint('[ERR] 会话初始化失败', Fore.RED, bright=True)} {e}", file=sys.stderr)
        return 1

    UI.panel(
        "Conversation",
        (
            f"provider   {config.provider}\n"
            f"model      {config.model}\n"
            f"max steps  {config.max_steps}\n"
            f"advanced   {format_advanced_feature_status(config)}\n"
            f"trace      {trace_path}"
        ),
        color=Fore.CYAN,
    )

    turn = 0
    reason = "eof"
    try:
        while True:
            # 用 readline() 而不是 `for line in sys.stdin`：后者有读前缓冲，
            # 会把已经写进管道的一行压着不放，多轮对话就会莫名卡住。
            line = sys.stdin.readline()
            if line == "":
                break  # EOF：调用方关掉了 stdin
            message = _read_conversation_message(line)
            if message is None:
                continue

            if message.get("type") == "reset":
                agent.reset_conversation()
                if trace_writer:
                    trace_writer.record("conversation_reset", {"after_turns": turn})
                UI.status("ok", "对话历史与本地记忆已重置")
                continue

            task = str(message.get("task") or "").strip()
            if not task:
                continue

            turn += 1
            UI.status("run", f"第 {turn} 轮", task[:80])
            try:
                result = agent.run(task)
            except LLMError as e:
                # 单轮失败不该杀掉整个会话——记一条证据，继续等下一轮。
                if trace_writer:
                    trace_writer.record(
                        "run_error",
                        {"error_type": "LLMError", "message": str(e), "turn": turn},
                    )
                UI.status("error", f"第 {turn} 轮 API 错误", str(e))
                continue
            except Exception as e:
                if trace_writer:
                    trace_writer.record(
                        "run_error",
                        {"error_type": type(e).__name__, "message": str(e), "turn": turn},
                    )
                UI.status("error", f"第 {turn} 轮失败", str(e))
                continue

            metadata = result.get("metadata", {})
            UI.status(
                "ok",
                f"第 {turn} 轮结束",
                f"{metadata.get('status', '?')} | {format_agent_context_status(agent)}",
            )
        return 0
    except KeyboardInterrupt:
        reason = "interrupted"
        return 0
    finally:
        if trace_writer:
            trace_writer.record("conversation_end", {"turns": turn, "reason": reason})
            trace_writer.close()
        mcp_manager.stop_all()
