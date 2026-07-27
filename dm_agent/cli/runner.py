"""Agent 装配与单任务执行：把 Config 翻译成 ReactAgent 并跑完一次 run。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dm_agent import (
    CriticAgent,
    LLMError,
    ReactAgent,
    Tool,
    create_llm_client,
    default_tools,
)
from dm_agent.core.checkpoint import RunCheckpoint
from dm_agent.core.reflexion import EpisodicMemory
from dm_agent.mcp import MCPManager, load_mcp_config
from dm_agent.skills import SkillManager
from dm_agent.tracing import TraceWriter

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
    trace_writer: TraceWriter | None = None,
    reflexion_memory: EpisodicMemory | None = None,
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
        enable_memory_hygiene=advanced["memory_hygiene"],
        enable_llm_compression=advanced["llm_compression"],
        enable_circuit_breaker=advanced["circuit_breaker"],
        circuit_breaker_threshold=config.circuit_breaker_threshold,
        circuit_breaker_cooldown=config.circuit_breaker_cooldown,
        enable_reflexion=advanced["reflexion"],
        max_trials=config.max_trials,
        reflexion_memory=reflexion_memory,
        critic=CriticAgent(client) if advanced["critic"] else None,
        enable_adaptive_replanning=advanced["adaptive_replanning"],
        max_replans=config.max_replans,
        enable_repeated_failure_policy_experiment=(advanced["repeated_failure_policy_experiment"]),
        event_bus=(
            extension_registry.create_event_bus() if extension_registry is not None else None
        ),
    )


def load_reflexion_memory_file(path_value: str) -> EpisodicMemory | None:
    """从文件加载持久化的 Reflexion 经验；文件不存在时返回空记忆。"""
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return EpisodicMemory()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return EpisodicMemory.from_dict(data)
    except (OSError, ValueError) as e:
        UI.status("warn", "Reflexion 记忆文件加载失败，使用空记忆", str(e))
        return EpisodicMemory()


def save_reflexion_memory_file(path_value: str, memory: EpisodicMemory | None) -> None:
    if not path_value or memory is None:
        return
    path = Path(path_value)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        tmp_path.write_text(
            json.dumps(memory.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp_path, path)
    except OSError as e:
        UI.status("warn", "Reflexion 记忆文件保存失败", str(e))


def format_agent_context_status(agent: ReactAgent) -> str:
    stats = agent.get_context_stats()
    return (
        f"history={stats['conversation_messages']} messages | "
        f"memory={stats['memory_items']} items | "
        f"compression={'on' if stats['compression_enabled'] else 'off'}"
    )


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
    trace_writer: TraceWriter | None = None

    try:
        # 启动 MCP 服务器
        started_count = mcp_manager.start_all()
        if started_count > 0:
            UI.status("ok", f"启动了 {started_count} 个 MCP 服务器")

        # 获取工具
        mcp_tools = mcp_manager.get_tools()
        tools = default_tools(
            include_mcp=True,
            mcp_tools=mcp_tools,
            extension_registry=extension_registry,
        )

        # 初始化技能管理器
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
                    "max_observation_chars": config.max_observation_chars,
                    "context_token_budget": config.context_token_budget,
                    "edit_guard_enabled": config.enable_edit_guard,
                    "mcp_started_count": started_count,
                    "mcp_tool_count": len(mcp_tools),
                    "skill_count": skill_count,
                    "trace_llm_io": trace_llm_io,
                    "reflexion_enabled": advanced["reflexion"],
                    "max_trials": config.max_trials,
                    "critic_enabled": advanced["critic"],
                    "adaptive_replanning_enabled": advanced["adaptive_replanning"],
                    "max_replans": config.max_replans,
                    "repeated_failure_policy_experiment_enabled": (
                        advanced["repeated_failure_policy_experiment"]
                    ),
                    "evolution_enabled": advanced["evolution"],
                },
            )

        # 创建步骤回调函数
        step_callback = create_step_callback(config.show_steps)

        reflexion_memory = load_reflexion_memory_file(config.reflexion_memory_file)
        agent = create_agent(
            config,
            client,
            tools,
            step_callback=step_callback,
            skill_manager=skill_manager,
            trace_writer=trace_writer,
            reflexion_memory=reflexion_memory,
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
        save_reflexion_memory_file(config.reflexion_memory_file, agent.reflexion_memory)
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
