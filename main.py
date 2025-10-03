"""LLM 驱动的 ReAct 智能体的 CLI 入口点。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
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

    class Style:
        BRIGHT = ""
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


def load_config_from_file() -> Dict[str, Any]:
    """从配置文件加载设置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ 配置文件加载失败：{e}，使用默认设置{Style.RESET_ALL}")
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
        print(f"{Fore.GREEN}✓ 配置已保存{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}✗ 配置保存失败：{e}{Style.RESET_ALL}")


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
    return parser.parse_args(argv)


def print_separator(char: str = "=", length: int = 70) -> None:
    """打印分隔线"""
    print(f"{Fore.CYAN}{char * length}{Style.RESET_ALL}")


def print_header(text: str) -> None:
    """打印标题"""
    print_separator()
    print(f"{Fore.GREEN}{Style.BRIGHT}{text.center(70)}{Style.RESET_ALL}")
    print_separator()


def print_welcome() -> None:
    """打印欢迎界面"""
    print("\n")
    print_header("DM-Code-Agent")
    print(f"{Fore.YELLOW}欢迎使用 LLM 驱动的 DM-Code-Agent 智能体系统！{Style.RESET_ALL}")

    # 显示配置文件状态
    if os.path.exists(CONFIG_FILE):
        print(f"{Fore.GREEN}✓ 已加载配置文件: config.json{Style.RESET_ALL}")
    else:
        print(f"{Fore.CYAN}ℹ 使用默认配置 (max_steps=100, temperature=0.7){Style.RESET_ALL}")
    print()


def print_menu() -> None:
    """打印主菜单"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}主菜单：{Style.RESET_ALL}")
    print(f"{Fore.GREEN}  1.{Style.RESET_ALL} 执行新任务")
    print(f"{Fore.GREEN}  2.{Style.RESET_ALL} 多轮对话模式")
    print(f"{Fore.GREEN}  3.{Style.RESET_ALL} 查看可用工具列表")
    print(f"{Fore.GREEN}  4.{Style.RESET_ALL} 配置设置")
    print(f"{Fore.GREEN}  5.{Style.RESET_ALL} 退出程序")
    print()


def show_tools(tools: List[Tool]) -> None:
    """显示可用工具列表"""
    print_separator("-")
    print(f"{Fore.CYAN}{Style.BRIGHT}可用工具列表：{Style.RESET_ALL}\n")

    for idx, tool in enumerate(tools, start=1):
        print(f"{Fore.GREEN}{idx}. {tool.name}{Style.RESET_ALL}")
        print(f"   {Fore.YELLOW}描述：{Style.RESET_ALL}{tool.description}")
        print()

    print_separator("-")


def configure_settings(config: Config) -> None:
    """配置设置"""
    print_separator("-")
    print(f"{Fore.CYAN}{Style.BRIGHT}当前配置：{Style.RESET_ALL}\n")
    print(f"  提供商：{Fore.YELLOW}{config.provider}{Style.RESET_ALL}")
    print(f"  模型：{Fore.YELLOW}{config.model}{Style.RESET_ALL}")
    print(f"  Base URL：{Fore.YELLOW}{config.base_url}{Style.RESET_ALL}")
    print(f"  最大步骤数：{Fore.YELLOW}{config.max_steps}{Style.RESET_ALL}")
    print(f"  温度：{Fore.YELLOW}{config.temperature}{Style.RESET_ALL}")
    print(f"  显示步骤：{Fore.YELLOW}{'是' if config.show_steps else '否'}{Style.RESET_ALL}")
    print()

    print(f"{Fore.CYAN}选择要修改的设置（直接回车跳过）：{Style.RESET_ALL}\n")

    config_changed = False

    # 修改提供商
    provider_input = input(f"LLM 提供商 (deepseek/openai/claude/gemini) [{config.provider}]: ").strip().lower()
    if provider_input and provider_input in ["deepseek", "openai", "claude", "gemini"]:
        if provider_input != config.provider:
            # 尝试获取新提供商的 API 密钥
            new_api_key = get_api_key_for_provider(provider_input)
            if not new_api_key:
                print(f"{Fore.RED}✗ 未找到 {provider_input.upper()}_API_KEY 环境变量{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}请在 .env 文件中配置 {provider_input.upper()}_API_KEY{Style.RESET_ALL}")
            else:
                config.provider = provider_input
                config.api_key = new_api_key  # 更新 API 密钥
                # 自动更新默认模型和 base_url
                defaults = PROVIDER_DEFAULTS.get(provider_input, {})
                config.model = defaults.get("model", config.model)
                config.base_url = defaults.get("base_url", config.base_url)
                config_changed = True
                print(f"{Fore.GREEN}✓ 已更新提供商为 {provider_input}，模型和 URL 已自动调整{Style.RESET_ALL}")
    elif provider_input and provider_input not in ["deepseek", "openai", "claude", "gemini"]:
        print(f"{Fore.RED}✗ 无效的提供商{Style.RESET_ALL}")

    # 修改模型
    model_input = input(f"模型名称 [{config.model}]: ").strip()
    if model_input:
        config.model = model_input
        config_changed = True
        print(f"{Fore.GREEN}✓ 已更新模型为 {model_input}{Style.RESET_ALL}")

    # 修改 Base URL
    base_url_input = input(f"Base URL [{config.base_url}]: ").strip()
    if base_url_input:
        config.base_url = base_url_input
        config_changed = True
        print(f"{Fore.GREEN}✓ 已更新 Base URL 为 {base_url_input}{Style.RESET_ALL}")

    # 修改最大步骤数
    try:
        max_steps_input = input(f"最大步骤数 [{config.max_steps}]: ").strip()
        if max_steps_input:
            new_max_steps = int(max_steps_input)
            if new_max_steps > 0:
                config.max_steps = new_max_steps
                config_changed = True
                print(f"{Fore.GREEN}✓ 已更新最大步骤数为 {new_max_steps}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}✗ 最大步骤数必须大于 0{Style.RESET_ALL}")
    except ValueError:
        print(f"{Fore.RED}✗ 无效的数字{Style.RESET_ALL}")

    # 修改温度
    try:
        temp_input = input(f"温度 (0.0-2.0) [{config.temperature}]: ").strip()
        if temp_input:
            new_temp = float(temp_input)
            if 0.0 <= new_temp <= 2.0:
                config.temperature = new_temp
                config_changed = True
                print(f"{Fore.GREEN}✓ 已更新温度为 {new_temp}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}✗ 温度必须在 0.0 到 2.0 之间{Style.RESET_ALL}")
    except ValueError:
        print(f"{Fore.RED}✗ 无效的数字{Style.RESET_ALL}")

    # 修改显示步骤
    show_steps_input = input(f"显示步骤 (y/n) [{'y' if config.show_steps else 'n'}]: ").strip().lower()
    if show_steps_input in ['y', 'yes', '是']:
        if not config.show_steps:
            config.show_steps = True
            config_changed = True
        print(f"{Fore.GREEN}✓ 已启用显示步骤{Style.RESET_ALL}")
    elif show_steps_input in ['n', 'no', '否']:
        if config.show_steps:
            config.show_steps = False
            config_changed = True
        print(f"{Fore.GREEN}✓ 已禁用显示步骤{Style.RESET_ALL}")

    # 保存配置
    if config_changed:
        print()
        save_choice = input(f"{Fore.CYAN}是否保存为永久配置？(y/n) [y]: {Style.RESET_ALL}").strip().lower()
        if save_choice in ['', 'y', 'yes', '是']:
            save_config_to_file(config)

    print_separator("-")


def display_result(result: Dict[str, Any], show_steps: bool = False) -> None:
    """格式化显示任务结果"""
    print_separator("-")

    if show_steps and result.get("steps"):
        print(f"{Fore.CYAN}{Style.BRIGHT}执行步骤：{Style.RESET_ALL}\n")
        for idx, step in enumerate(result.get("steps", []), start=1):
            print(f"{Fore.MAGENTA}步骤 {idx}:{Style.RESET_ALL}")
            print(f"  {Fore.YELLOW}思考：{Style.RESET_ALL}{step.get('thought')}")
            print(f"  {Fore.YELLOW}动作：{Style.RESET_ALL}{step.get('action')}")
            action_input = step.get('action_input')
            if action_input:
                print(f"  {Fore.YELLOW}输入：{Style.RESET_ALL}{json.dumps(action_input, ensure_ascii=False)}")
            print(f"  {Fore.YELLOW}观察：{Style.RESET_ALL}{step.get('observation')}")
            print()

    print(f"{Fore.GREEN}{Style.BRIGHT}最终答案：{Style.RESET_ALL}\n")
    final_answer = result.get("final_answer", "")
    print(final_answer)
    print()
    print_separator("-")


def create_step_callback(show_steps: bool):
    """创建步骤回调函数，用于实时打印 agent 执行状态"""
    def callback(step_num: int, step: Any) -> None:
        if show_steps:
            print(f"\n{Fore.MAGENTA}{Style.BRIGHT}[步骤 {step_num}]{Style.RESET_ALL}")
            print(f"  {Fore.YELLOW}思考：{Style.RESET_ALL}{step.thought}")
            print(f"  {Fore.YELLOW}动作：{Style.RESET_ALL}{step.action}")
            if step.action_input:
                print(f"  {Fore.YELLOW}输入：{Style.RESET_ALL}{json.dumps(step.action_input, ensure_ascii=False)}")
            print(f"  {Fore.YELLOW}观察：{Style.RESET_ALL}{step.observation}")
        else:
            # 即使不显示详细步骤，也显示简要进度
            print(f"{Fore.CYAN}[步骤 {step_num}] {step.action}{Style.RESET_ALL}", end=" ", flush=True)
            if step.action == "finish" or step.action == "task_complete":
                print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
            elif step.action == "error":
                print(f"{Fore.RED}✗{Style.RESET_ALL}")
            else:
                print(f"{Fore.GREEN}✓{Style.RESET_ALL}")

    return callback


def multi_turn_conversation(config: Config, tools: List[Tool]) -> None:
    """多轮对话模式"""
    print_separator("-")
    print(f"{Fore.CYAN}{Style.BRIGHT}多轮对话模式{Style.RESET_ALL}\n")
    print(f"{Fore.YELLOW}进入多轮对话模式，智能体会记住之前的所有对话内容{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}输入 'exit' 退出对话模式，输入 'reset' 重置对话历史{Style.RESET_ALL}\n")
    print_separator("-")

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
        )

        conversation_count = 0

        while True:
            print(f"\n{Fore.CYAN}[对话 {conversation_count + 1}]{Style.RESET_ALL}")
            task = input(f"{Fore.YELLOW}请输入任务（exit 退出，reset 重置历史）：{Style.RESET_ALL}\n> ").strip()

            if not task:
                print(f"{Fore.RED}✗ 任务描述不能为空{Style.RESET_ALL}")
                continue

            if task.lower() == "exit":
                print(f"\n{Fore.YELLOW}退出多轮对话模式{Style.RESET_ALL}")
                break

            if task.lower() == "reset":
                agent.reset_conversation()
                conversation_count = 0
                print(f"{Fore.GREEN}✓ 对话历史已重置{Style.RESET_ALL}")
                continue

            try:
                print(f"\n{Fore.CYAN}正在执行任务...{Style.RESET_ALL}\n")
                print_separator("-")

                # 执行任务
                result = agent.run(task)
                conversation_count += 1

                # 显示最终结果
                print(f"\n{Fore.GREEN}{Style.BRIGHT}最终答案：{Style.RESET_ALL}\n")
                print(result.get("final_answer", ""))
                print()
                print_separator("-")

            except LLMError as e:
                print(f"\n{Fore.RED}{Style.BRIGHT}✗ API 错误：{Style.RESET_ALL}{e}")
                print_separator("-")
            except KeyboardInterrupt:
                print(f"\n\n{Fore.YELLOW}退出多轮对话模式{Style.RESET_ALL}")
                break
            except Exception as e:
                print(f"\n{Fore.RED}{Style.BRIGHT}✗ 发生错误：{Style.RESET_ALL}{e}")
                print_separator("-")

    except Exception as e:
        print(f"\n{Fore.RED}{Style.BRIGHT}✗ 初始化错误：{Style.RESET_ALL}{e}")
        print_separator("-")


def execute_task(config: Config, tools: List[Tool]) -> None:
    """执行任务"""
    print_separator("-")
    print(f"{Fore.CYAN}{Style.BRIGHT}执行新任务{Style.RESET_ALL}\n")
    print(f"{Fore.YELLOW}请输入任务描述（输入完成后按回车）：{Style.RESET_ALL}")

    task = input("> ").strip()

    if not task:
        print(f"{Fore.RED}✗ 任务描述不能为空{Style.RESET_ALL}")
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
        )

        print(f"\n{Fore.CYAN}正在执行任务...{Style.RESET_ALL}\n")
        print_separator("-")

        # 执行任务
        result = agent.run(task)

        # 显示最终结果
        print(f"\n{Fore.GREEN}{Style.BRIGHT}最终答案：{Style.RESET_ALL}\n")
        print(result.get("final_answer", ""))
        print()
        print_separator("-")

    except LLMError as e:
        print(f"\n{Fore.RED}{Style.BRIGHT}✗ API 错误：{Style.RESET_ALL}{e}")
        print_separator("-")
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}任务已被用户中断{Style.RESET_ALL}")
        print_separator("-")
    except Exception as e:
        print(f"\n{Fore.RED}{Style.BRIGHT}✗ 发生错误：{Style.RESET_ALL}{e}")
        print_separator("-")


def interactive_mode(config: Config) -> int:
    """交互式菜单模式"""
    print_welcome()

    # 初始化 MCP 管理器
    mcp_config = load_mcp_config()
    mcp_manager = MCPManager(mcp_config)

    # 启动所有启用的 MCP 服务器
    print(f"{Fore.CYAN}正在加载 MCP 服务器...{Style.RESET_ALL}")
    started_count = mcp_manager.start_all()
    if started_count > 0:
        print(f"{Fore.GREEN}✓ 成功启动 {started_count} 个 MCP 服务器{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}ℹ 未启用 MCP 服务器{Style.RESET_ALL}")

    # 获取包含 MCP 工具的工具列表
    mcp_tools = mcp_manager.get_tools()
    tools = default_tools(include_mcp=True, mcp_tools=mcp_tools)

    if mcp_tools:
        print(f"{Fore.GREEN}✓ 加载了 {len(mcp_tools)} 个 MCP 工具{Style.RESET_ALL}")

    try:
        while True:
            try:
                print_menu()
                choice = input(f"{Fore.CYAN}请选择操作 (1-5): {Style.RESET_ALL}").strip()

                if choice == "1":
                    # 执行新任务
                    execute_task(config, tools)

                elif choice == "2":
                    # 多轮对话模式
                    multi_turn_conversation(config, tools)

                elif choice == "3":
                    # 查看工具列表
                    show_tools(tools)

                elif choice == "4":
                    # 配置设置
                    configure_settings(config)

                elif choice == "5":
                    # 退出程序
                    print(f"\n{Fore.YELLOW}感谢使用！再见！{Style.RESET_ALL}\n")
                    return 0

                else:
                    print(f"{Fore.RED}✗ 无效的选择，请输入 1-5{Style.RESET_ALL}")

            except KeyboardInterrupt:
                print(f"\n\n{Fore.YELLOW}感谢使用！再见！{Style.RESET_ALL}\n")
                return 0
            except EOFError:
                print(f"\n\n{Fore.YELLOW}感谢使用！再见！{Style.RESET_ALL}\n")
                return 0
            except Exception as e:
                print(f"\n{Fore.RED}{Style.BRIGHT}✗ 发生错误：{Style.RESET_ALL}{e}\n")

    finally:
        # 清理 MCP 资源
        print(f"{Fore.CYAN}正在关闭 MCP 服务器...{Style.RESET_ALL}")
        mcp_manager.stop_all()
        print(f"{Fore.GREEN}✓ MCP 服务器已关闭{Style.RESET_ALL}")


def run_single_task(config: Config, task: str) -> int:
    """运行单个任务（命令行模式）"""
    # 初始化 MCP
    mcp_config = load_mcp_config()
    mcp_manager = MCPManager(mcp_config)

    try:
        # 启动 MCP 服务器
        started_count = mcp_manager.start_all()
        if started_count > 0:
            print(f"{Fore.GREEN}✓ 启动了 {started_count} 个 MCP 服务器{Style.RESET_ALL}")

        # 获取工具
        mcp_tools = mcp_manager.get_tools()
        tools = default_tools(include_mcp=True, mcp_tools=mcp_tools)

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
        )

        print(f"\n{Fore.CYAN}正在执行任务：{Style.RESET_ALL}{task}\n")
        print_separator()

        result = agent.run(task)

        # 显示最终结果
        print(f"\n{Fore.GREEN}{Style.BRIGHT}最终答案：{Style.RESET_ALL}\n")
        print(result.get("final_answer", ""))
        print()
        print_separator()

        return 0

    except LLMError as e:
        print(f"{Fore.RED}{Style.BRIGHT}✗ API 错误：{Style.RESET_ALL}{e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"{Fore.RED}{Style.BRIGHT}✗ 发生错误：{Style.RESET_ALL}{e}", file=sys.stderr)
        return 1
    finally:
        # 清理 MCP 资源
        mcp_manager.stop_all()


def main(argv: Any = None) -> int:
    """主入口函数"""
    load_dotenv()
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # 如果没有提供 API 密钥，尝试根据提供商获取
    if not args.api_key:
        args.api_key = get_api_key_for_provider(args.provider)

    # 检查 API 密钥
    if not args.api_key:
        print(f"{Fore.RED}✗ 缺少 API 密钥。{Style.RESET_ALL}", file=sys.stderr)
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
        return run_single_task(config, args.task)

    # 如果指定了交互模式或没有提供任务，进入交互式菜单
    if args.interactive or not args.task:
        return interactive_mode(config)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
