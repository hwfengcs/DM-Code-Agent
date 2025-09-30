"""DeepSeek 驱动的 ReAct 智能体的 CLI 入口点。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List

from dotenv import load_dotenv

from deepseek_agent import DeepSeekClient, DeepSeekError, ReactAgent, Tool, default_tools

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
    model: str = "deepseek-chat"
    max_steps: int = 8
    temperature: float = 0.0
    show_steps: bool = False


def parse_args(argv: Any) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行基于 DeepSeek 的 ReAct 智能体来完成任务描述。")
    parser.add_argument("task", nargs="?", help="智能体要完成的自然语言任务。")
    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=os.getenv("DEEPSEEK_API_KEY"),
        help="DeepSeek API 密钥（默认使用环境变量 DEEPSEEK_API_KEY）。",
    )
    parser.add_argument(
        "--model",
        default="deepseek-chat",
        help="DeepSeek 模型标识符（默认：deepseek-chat）。",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
        help="放弃前的最大推理/工具步骤数（默认：8）。",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="模型的采样温度（默认：0.0）。",
    )
    parser.add_argument(
        "--show-steps",
        action="store_true",
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
    print_header("DeepSeek ReAct 智能体")
    print(f"{Fore.YELLOW}欢迎使用 DeepSeek 驱动的 ReAct 智能体系统！{Style.RESET_ALL}")
    print()


def print_menu() -> None:
    """打印主菜单"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}主菜单：{Style.RESET_ALL}")
    print(f"{Fore.GREEN}  1.{Style.RESET_ALL} 执行新任务")
    print(f"{Fore.GREEN}  2.{Style.RESET_ALL} 查看可用工具列表")
    print(f"{Fore.GREEN}  3.{Style.RESET_ALL} 配置设置")
    print(f"{Fore.GREEN}  4.{Style.RESET_ALL} 退出程序")
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
    print(f"  模型：{Fore.YELLOW}{config.model}{Style.RESET_ALL}")
    print(f"  最大步骤数：{Fore.YELLOW}{config.max_steps}{Style.RESET_ALL}")
    print(f"  温度：{Fore.YELLOW}{config.temperature}{Style.RESET_ALL}")
    print(f"  显示步骤：{Fore.YELLOW}{'是' if config.show_steps else '否'}{Style.RESET_ALL}")
    print()

    print(f"{Fore.CYAN}选择要修改的设置（直接回车跳过）：{Style.RESET_ALL}\n")

    # 修改最大步骤数
    try:
        max_steps_input = input(f"最大步骤数 [{config.max_steps}]: ").strip()
        if max_steps_input:
            new_max_steps = int(max_steps_input)
            if new_max_steps > 0:
                config.max_steps = new_max_steps
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
                print(f"{Fore.GREEN}✓ 已更新温度为 {new_temp}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}✗ 温度必须在 0.0 到 2.0 之间{Style.RESET_ALL}")
    except ValueError:
        print(f"{Fore.RED}✗ 无效的数字{Style.RESET_ALL}")

    # 修改显示步骤
    show_steps_input = input(f"显示步骤 (y/n) [{'y' if config.show_steps else 'n'}]: ").strip().lower()
    if show_steps_input in ['y', 'yes', '是']:
        config.show_steps = True
        print(f"{Fore.GREEN}✓ 已启用显示步骤{Style.RESET_ALL}")
    elif show_steps_input in ['n', 'no', '否']:
        config.show_steps = False
        print(f"{Fore.GREEN}✓ 已禁用显示步骤{Style.RESET_ALL}")

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
        client = DeepSeekClient(api_key=config.api_key, model=config.model)
        agent = ReactAgent(
            client,
            tools,
            max_steps=config.max_steps,
            temperature=config.temperature,
        )

        print(f"\n{Fore.CYAN}正在执行任务...{Style.RESET_ALL}\n")
        print_separator("-")

        # 执行任务
        result = agent.run(task)

        # 显示结果
        display_result(result, config.show_steps)

    except DeepSeekError as e:
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

    tools = default_tools()

    while True:
        try:
            print_menu()
            choice = input(f"{Fore.CYAN}请选择操作 (1-4): {Style.RESET_ALL}").strip()

            if choice == "1":
                # 执行新任务
                execute_task(config, tools)

            elif choice == "2":
                # 查看工具列表
                show_tools(tools)

            elif choice == "3":
                # 配置设置
                configure_settings(config)

            elif choice == "4":
                # 退出程序
                print(f"\n{Fore.YELLOW}感谢使用！再见！{Style.RESET_ALL}\n")
                return 0

            else:
                print(f"{Fore.RED}✗ 无效的选择，请输入 1-4{Style.RESET_ALL}")

        except KeyboardInterrupt:
            print(f"\n\n{Fore.YELLOW}感谢使用！再见！{Style.RESET_ALL}\n")
            return 0
        except EOFError:
            print(f"\n\n{Fore.YELLOW}感谢使用！再见！{Style.RESET_ALL}\n")
            return 0
        except Exception as e:
            print(f"\n{Fore.RED}{Style.BRIGHT}✗ 发生错误：{Style.RESET_ALL}{e}\n")


def run_single_task(config: Config, task: str) -> int:
    """运行单个任务（命令行模式）"""
    try:
        client = DeepSeekClient(api_key=config.api_key, model=config.model)
        tools = default_tools()
        agent = ReactAgent(
            client,
            tools,
            max_steps=config.max_steps,
            temperature=config.temperature,
        )

        print(f"\n{Fore.CYAN}正在执行任务：{Style.RESET_ALL}{task}\n")
        print_separator()

        result = agent.run(task)

        display_result(result, config.show_steps)

        return 0

    except DeepSeekError as e:
        print(f"{Fore.RED}{Style.BRIGHT}✗ API 错误：{Style.RESET_ALL}{e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"{Fore.RED}{Style.BRIGHT}✗ 发生错误：{Style.RESET_ALL}{e}", file=sys.stderr)
        return 1


def main(argv: Any = None) -> int:
    """主入口函数"""
    load_dotenv()
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # 检查 API 密钥
    if not args.api_key:
        print(f"{Fore.RED}✗ 缺少 DeepSeek API 密钥。{Style.RESET_ALL}", file=sys.stderr)
        print("请提供 --api-key 或设置 DEEPSEEK_API_KEY 环境变量。", file=sys.stderr)
        return 2

    # 创建配置
    config = Config(
        api_key=args.api_key,
        model=args.model,
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
