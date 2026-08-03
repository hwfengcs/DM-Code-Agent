"""交互式菜单模式：欢迎页、设置向导、单次任务与多轮对话循环。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dm_agent import (
    PROVIDER_DEFAULTS,
    LLMError,
    Tool,
    create_llm_client,
    default_tools,
)
from dm_agent.mcp import MCPManager, load_mcp_config
from dm_agent.paths import resolve_config_read_path
from dm_agent.skills import SkillManager

from .config import (
    Config,
    format_advanced_feature_status,
    format_missing_api_key_help,
    get_api_key_for_provider,
    save_config_to_file,
)
from .report import collect_git_status
from .runner import (
    create_agent,
    format_agent_context_status,
    review_completed_run,
)
from .ui import UI, ask_bool_setting, create_step_callback, print_menu, show_skills, show_tools

if TYPE_CHECKING:
    from dm_agent.extensions import ExtensionRegistry


def print_welcome() -> None:
    """打印欢迎界面"""
    UI.banner("DM-Code-Agent", "Local-first code agent with trace, tools, skills, and memory.")

    # 打完整路径而不是「config.json」：全局安装后配置可能来自项目级也可能来自用户级，
    # 只说文件名等于没说。
    source = resolve_config_read_path()
    if source is not None:
        UI.status("ok", "已加载配置文件", str(source))
    else:
        UI.status("info", "使用默认配置", "max_steps=100 | temperature=0.7")
    print()


def configure_settings(config: Config, extension_registry: ExtensionRegistry | None = None) -> None:
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
            ("Advanced", format_advanced_feature_status(config)),
            ("Max replans", config.max_replans),
        ],
    )
    UI.status("info", "选择要修改的设置", "直接回车跳过")
    print()

    config_changed = False
    provider_names = (
        extension_registry.get_provider_names()
        if extension_registry is not None
        else list(PROVIDER_DEFAULTS)
    )

    # 修改提供商
    provider_input = (
        UI.ask(
            "LLM 提供商",
            choices=provider_names,
            default=config.provider,
        )
        .strip()
        .lower()
    )
    if provider_input and provider_input in provider_names:
        if provider_input != config.provider:
            # 尝试获取新提供商的 API 密钥
            new_api_key = get_api_key_for_provider(provider_input)
            if provider_input in PROVIDER_DEFAULTS and not new_api_key:
                UI.status("error", f"未找到 {provider_input.upper()}_API_KEY")
                # 给完整路径而不是「请在 .env 中配置」——用户此刻正在切换供应商，
                # 需要知道那个文件到底该建在哪。
                print(format_missing_api_key_help(provider_input))
            else:
                config.provider = provider_input
                config.api_key = new_api_key or ""
                # 自动更新默认模型和 base_url
                defaults = PROVIDER_DEFAULTS.get(provider_input, {})
                config.model = defaults.get("model", config.model)
                config.base_url = defaults.get("base_url", config.base_url)
                config_changed = True
                UI.status("ok", f"已更新提供商为 {provider_input}", "模型和 URL 已自动调整")
    elif provider_input and provider_input not in provider_names:
        UI.status("error", "无效的提供商")

    # 修改模型
    model_input = UI.ask("模型名称", default=config.model).strip()
    if model_input and model_input != config.model:
        config.model = model_input
        config_changed = True
        UI.status("ok", f"已更新模型为 {model_input}")

    # 修改 Base URL
    base_url_input = UI.ask("Base URL", default=config.base_url).strip()
    if base_url_input and base_url_input != config.base_url:
        config.base_url = base_url_input
        config_changed = True
        UI.status("ok", f"已更新 Base URL 为 {base_url_input}")

    # 修改最大步骤数
    try:
        max_steps_input = UI.ask("最大步骤数", default=str(config.max_steps)).strip()
        if max_steps_input:
            new_max_steps = int(max_steps_input)
            if new_max_steps > 0:
                if new_max_steps != config.max_steps:
                    config.max_steps = new_max_steps
                    config_changed = True
                    UI.status("ok", f"已更新最大步骤数为 {new_max_steps}")
            else:
                UI.status("error", "最大步骤数必须大于 0")
    except ValueError:
        UI.status("error", "无效的数字")

    # 修改温度
    try:
        temp_input = UI.ask("温度 (0.0-2.0)", default=str(config.temperature)).strip()
        if temp_input:
            new_temp = float(temp_input)
            if 0.0 <= new_temp <= 2.0:
                if new_temp != config.temperature:
                    config.temperature = new_temp
                    config_changed = True
                    UI.status("ok", f"已更新温度为 {new_temp}")
            else:
                UI.status("error", "温度必须在 0.0 到 2.0 之间")
    except ValueError:
        UI.status("error", "无效的数字")

    # 修改显示步骤
    new_show_steps = ask_bool_setting("显示步骤", config.show_steps)
    if new_show_steps != config.show_steps:
        config.show_steps = new_show_steps
        config_changed = True
    UI.status("ok", "已启用显示步骤" if config.show_steps else "已禁用显示步骤")

    UI.section(
        "高级功能",
        "这些能力会增加模型调用或改变恢复策略；默认关闭，建议按任务显式启用。",
    )

    new_adaptive = ask_bool_setting("启用自适应重规划", config.enable_adaptive_replanning)
    if new_adaptive != config.enable_adaptive_replanning:
        config.enable_adaptive_replanning = new_adaptive
        config_changed = True
    if config.enable_adaptive_replanning:
        try:
            max_replans_input = UI.ask(
                "最大重规划次数 (-1 表示不限)", default=str(config.max_replans)
            ).strip()
            if max_replans_input:
                new_max_replans = int(max_replans_input)
                if new_max_replans >= -1:
                    if new_max_replans != config.max_replans:
                        config.max_replans = new_max_replans
                        config_changed = True
                else:
                    UI.status("error", "最大重规划次数必须为 -1 或更大")
        except ValueError:
            UI.status("error", "无效的数字")

    # 保存配置
    if config_changed:
        print()
        save_choice = (
            UI.ask("是否保存为永久配置？", choices=["y", "n"], default="y").strip().lower()
        )
        if save_choice in ["", "y", "yes", "是"]:
            save_config_to_file(config)

    print()


def multi_turn_conversation(
    config: Config,
    tools: list[Tool],
    skill_manager: SkillManager | None = None,
    extension_registry: ExtensionRegistry | None = None,
) -> None:
    """多轮对话模式"""
    UI.section(
        "多轮对话",
        "同一个 agent 实例会保留当前会话，并使用本地原子记忆整理旧上下文。"
        "这份记忆只在当前 CLI 进程内连续；输入 exit 退出，输入 reset 重置。",
    )

    try:
        # 创建客户端和智能体
        client = create_llm_client(
            provider=config.provider,
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
            respond_retries=config.llm_max_retries,
            extension_registry=extension_registry,
        )
        step_callback = create_step_callback(config.show_steps)

        agent = create_agent(
            config,
            client,
            tools,
            step_callback=step_callback,
            skill_manager=skill_manager,
            extension_registry=extension_registry,
        )

        conversation_count = 0

        while True:
            UI.section(f"对话 {conversation_count + 1}")
            UI.status("info", "当前会话记忆", format_agent_context_status(agent))
            task = UI.ask("请输入任务 (exit 退出，reset 重置历史)").strip()

            if not task:
                UI.status("error", "任务描述不能为空")
                continue

            if task.lower() == "exit":
                UI.status("info", "退出多轮对话模式")
                break

            if task.lower() == "reset":
                agent.reset_conversation()
                conversation_count = 0
                UI.status("ok", "对话历史和本地记忆已重置")
                continue

            try:
                UI.status("run", "正在执行任务")

                # 执行任务
                git_status_before = collect_git_status()
                result = agent.run(task)
                git_status_after = collect_git_status()
                conversation_count += 1

                metadata = result.get("metadata", {})
                context_status = (
                    f"{format_agent_context_status(agent)} | "
                    f"injections={metadata.get('memory_injection_count', 0)}"
                )
                review_completed_run(
                    result,
                    config=config,
                    task=task,
                    context_status=context_status,
                    git_status_before=git_status_before,
                    git_status_after=git_status_after,
                    interactive=True,
                )

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
    config: Config,
    tools: list[Tool],
    skill_manager: SkillManager | None = None,
    extension_registry: ExtensionRegistry | None = None,
) -> None:
    """执行任务"""
    UI.section("执行新任务")
    task = UI.ask("请输入任务描述").strip()

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
            respond_retries=config.llm_max_retries,
            extension_registry=extension_registry,
        )

        # 创建步骤回调函数
        step_callback = create_step_callback(config.show_steps)

        agent = create_agent(
            config,
            client,
            tools,
            step_callback=step_callback,
            skill_manager=skill_manager,
            extension_registry=extension_registry,
        )

        UI.status("run", "正在执行任务")

        # 执行任务
        git_status_before = collect_git_status()
        result = agent.run(task)
        git_status_after = collect_git_status()

        review_completed_run(
            result,
            config=config,
            task=task,
            git_status_before=git_status_before,
            git_status_after=git_status_after,
            interactive=True,
        )

    except LLMError as e:
        UI.status("error", "API 错误", str(e))
    except KeyboardInterrupt:
        UI.status("warn", "任务已被用户中断")
    except Exception as e:
        UI.status("error", "发生错误", str(e))


def interactive_mode(config: Config, extension_registry: ExtensionRegistry | None = None) -> int:
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
    tools = default_tools(
        include_mcp=True,
        mcp_tools=mcp_tools,
        extension_registry=extension_registry,
    )

    if mcp_tools:
        UI.status("ok", f"加载了 {len(mcp_tools)} 个 MCP 工具")

    # 初始化技能管理器
    skill_manager = SkillManager(extension_registry=extension_registry)
    skill_count = skill_manager.load_all()
    if skill_count > 0:
        UI.status("ok", f"加载了 {skill_count} 个技能")
    else:
        UI.status("info", "未加载任何技能")

    try:
        while True:
            try:
                print_menu()
                choice = UI.ask(
                    "选择操作 (1-6)",
                    choices=["1", "2", "3", "4", "5", "6"],
                    show_choices=False,
                ).strip()

                if choice == "1":
                    # 执行新任务
                    execute_task(config, tools, skill_manager, extension_registry)

                elif choice == "2":
                    # 多轮对话模式
                    multi_turn_conversation(config, tools, skill_manager, extension_registry)

                elif choice == "3":
                    # 查看工具列表
                    show_tools(tools)

                elif choice == "4":
                    # 配置设置
                    configure_settings(config, extension_registry)

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
