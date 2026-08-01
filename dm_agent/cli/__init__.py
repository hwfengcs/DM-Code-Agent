"""dm-agent 命令行入口。

历史上这些代码住在仓库根的顶级 main.py 里，会被 setuptools 装成 site-packages
顶层的 `main` 模块并污染用户命名空间。现按职责拆进本包：

    ui.py           渲染原语与只读界面（不依赖 Config）
    config.py       Config / config.json 读写 / 高级开关解析
    args.py         argparse 定义与参数校验
    report.py       Markdown 运行报告与 git 状态
    runner.py       agent 装配与单任务执行
    interactive.py  交互式菜单模式

依赖方向单向向下：__init__ → interactive → runner → report → config → ui。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from dm_agent import PROVIDER_DEFAULTS
from dm_agent.core.checkpoint import RunCheckpoint
from dm_agent.core.persistence import load_resume_state
from dm_agent.extensions import (
    ExtensionDiscoveryError,
    ProjectTrustDecision,
    discover_extensions,
)

from .args import parse_args, validate_feature_args
from .config import (
    CONFIG_FILE,
    Config,
    format_advanced_feature_status,
    get_api_key_for_provider,
    load_config_from_file,
    resolve_advanced_features,
    save_config_to_file,
)
from .interactive import (
    configure_settings,
    execute_task,
    interactive_mode,
    multi_turn_conversation,
    print_welcome,
)
from .report import collect_git_status, default_report_path, write_run_report
from .runner import (
    create_agent,
    format_agent_context_status,
    load_reflexion_memory_file,
    review_completed_run,
    run_conversation_stdin,
    run_single_task,
    save_reflexion_memory_file,
)
from .ui import (
    UI,
    Fore,
    ask_bool_setting,
    browse_run_steps,
    configure_console_encoding,
    create_step_callback,
    display_completion_screen,
    display_result,
    display_step_page,
    format_duration,
    format_run_status,
    format_step_input,
    print_header,
    print_menu,
    print_separator,
    show_skills,
    show_tools,
)

__all__ = [
    "CONFIG_FILE",
    "PROVIDER_DEFAULTS",
    "UI",
    "Config",
    "Fore",
    "ask_bool_setting",
    "browse_run_steps",
    "collect_git_status",
    "configure_console_encoding",
    "configure_settings",
    "create_agent",
    "create_step_callback",
    "default_report_path",
    "display_completion_screen",
    "display_result",
    "display_step_page",
    "execute_task",
    "format_advanced_feature_status",
    "format_agent_context_status",
    "format_duration",
    "format_run_status",
    "format_step_input",
    "get_api_key_for_provider",
    "interactive_mode",
    "load_config_from_file",
    "load_reflexion_memory_file",
    "main",
    "multi_turn_conversation",
    "parse_args",
    "print_header",
    "print_menu",
    "print_separator",
    "print_welcome",
    "resolve_advanced_features",
    "review_completed_run",
    "run_conversation_stdin",
    "run_single_task",
    "save_config_to_file",
    "save_reflexion_memory_file",
    "show_skills",
    "show_tools",
    "validate_feature_args",
    "write_run_report",
]


def main(argv: Any = None) -> int:
    """主入口函数"""
    configure_console_encoding()
    load_dotenv()
    args = parse_args(argv if argv is not None else sys.argv[1:])

    feature_error = validate_feature_args(args)
    if feature_error:
        print(UI.paint("[ERR] 高级功能参数无效", Fore.RED, bright=True), file=sys.stderr)
        print(feature_error, file=sys.stderr)
        return 2

    try:
        discovery = discover_extensions(
            project_root=Path.cwd(),
            no_extensions=args.no_extensions,
            explicit_paths=args.extension_paths,
            trust_prompt=(
                _prompt_project_extension_trust
                if sys.stdin.isatty() and sys.stdout.isatty()
                else None
            ),
        )
    except ExtensionDiscoveryError as e:
        print(UI.paint("[ERR] 扩展加载失败", Fore.RED, bright=True), file=sys.stderr)
        print(str(e), file=sys.stderr)
        return 2

    _display_extension_diagnostics(discovery.loaded, discovery.skipped)
    for failure in discovery.failures:
        UI.status("warn", f"扩展加载失败：{failure.source}", failure.message)
    extension_registry = discovery.registry

    if extension_registry.get_provider_factory(args.provider) is None:
        supported = ", ".join(extension_registry.get_provider_names())
        print(UI.paint("[ERR] 不支持的 LLM 提供商", Fore.RED, bright=True), file=sys.stderr)
        print(
            f"不支持的提供商: {args.provider}。支持的提供商: {supported}",
            file=sys.stderr,
        )
        return 2

    # 如果没有提供 API 密钥，尝试根据提供商获取
    if not args.api_key:
        args.api_key = get_api_key_for_provider(args.provider)

    provider_name = args.provider.casefold()

    # 四家内置供应商保持原有的 API key 前置校验；扩展供应商自行决定是否需要。
    if not args.api_key and provider_name in PROVIDER_DEFAULTS:
        print(UI.paint("[ERR] 缺少 API 密钥", Fore.RED, bright=True), file=sys.stderr)
        print(f"请提供 --api-key 或设置环境变量 {args.provider.upper()}_API_KEY。", file=sys.stderr)
        return 2
    args.api_key = args.api_key or ""

    # 获取提供商的默认配置
    provider_defaults = PROVIDER_DEFAULTS.get(provider_name, {})

    # 如果没有指定 base_url，使用提供商默认值
    if not args.base_url:
        args.base_url = provider_defaults.get("base_url", "")

    # 如果模型是默认的 deepseek-chat 但提供商不是 deepseek，更新模型
    if args.model == "deepseek-chat" and provider_name != "deepseek":
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
        max_observation_chars=args.max_observation_chars,
        context_token_budget=args.context_token_budget,
        enable_edit_guard=args.enable_edit_guard,
        llm_max_retries=args.llm_max_retries,
        enable_reflexion=args.enable_reflexion,
        max_trials=args.max_trials,
        enable_critic=args.enable_critic,
        enable_adaptive_replanning=args.enable_adaptive_replanning,
        max_replans=args.max_replans,
        enable_repeated_failure_policy_experiment=(args.enable_repeated_failure_policy_experiment),
        enable_evolution=args.enable_evolution,
        enable_memory_hygiene=args.enable_memory_hygiene,
        enable_llm_compression=args.enable_llm_compression,
        enable_circuit_breaker=args.enable_circuit_breaker,
        circuit_breaker_threshold=args.circuit_breaker_threshold,
        circuit_breaker_cooldown=args.circuit_breaker_cooldown,
        reflexion_memory_file=str(args.reflexion_memory_file or ""),
    )

    # --resume：从 checkpoint 恢复任务（任务参数可省略）
    resume_state: RunCheckpoint | None = None
    if args.resume:
        try:
            resume_state = load_resume_state(args.resume, at=args.resume_at or None)
        except ValueError as e:
            print(UI.paint("[ERR] checkpoint 加载失败", Fore.RED, bright=True), file=sys.stderr)
            print(str(e), file=sys.stderr)
            return 2
        if args.task and args.task.strip() != resume_state.task.strip():
            print(
                UI.paint("[ERR] --resume 的任务与命令行任务不一致", Fore.RED, bright=True),
                file=sys.stderr,
            )
            print("省略任务参数即可沿用 checkpoint 中的原始任务。", file=sys.stderr)
            return 2
        args.task = resume_state.task

    # 长驻会话模式：任务从 stdin 逐轮进来，共享同一个 agent 的对话历史。
    if args.conversation_stdin:
        return run_conversation_stdin(
            config,
            trace_path=args.trace,
            trace_llm_io=args.trace_llm_io,
            extension_registry=extension_registry,
        )

    # 如果提供了任务参数，直接执行任务
    if args.task:
        return run_single_task(
            config,
            args.task,
            trace_path=args.trace,
            trace_llm_io=args.trace_llm_io,
            report_path=args.report,
            checkpoint_path=args.checkpoint,
            resume_state=resume_state,
            extension_registry=extension_registry,
        )

    # 如果指定了交互模式或没有提供任务，进入交互式菜单
    if args.interactive or not args.task:
        return interactive_mode(config, extension_registry)

    return 0


def _prompt_project_extension_trust(project_root: Path) -> ProjectTrustDecision:
    UI.section(
        "项目扩展安全确认",
        "项目内 .dm_agent/extensions/*.py 会以当前用户权限执行任意代码。"
        "仅在你已审查并信任此仓库时加载。",
    )
    UI.status("warn", "待确认项目", str(project_root))
    choice = (
        UI.ask(
            "加载项目扩展？o=仅本次，a=始终信任，n=本次跳过，d=始终拒绝",
            choices=["o", "a", "n", "d"],
            default="n",
        )
        .strip()
        .lower()
    )
    return {
        "o": ProjectTrustDecision.LOAD_ONCE,
        "a": ProjectTrustDecision.TRUST,
        "d": ProjectTrustDecision.DENY,
    }.get(choice, ProjectTrustDecision.SKIP_ONCE)


def _display_extension_diagnostics(
    loaded: list[str],
    skipped: list[str],
) -> None:
    external_count = max(0, len(loaded) - 1)
    if external_count:
        UI.status("ok", f"已加载 {external_count} 个外部扩展")
    for source in skipped:
        UI.status("warn", "项目扩展未加载", source)
