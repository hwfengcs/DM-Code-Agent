"""命令行参数定义与校验。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .config import get_api_key_for_provider, load_config_from_file


def validate_feature_args(args: argparse.Namespace) -> str:
    """Validate default-off advanced feature CLI arguments."""
    if args.max_trials < 1:
        return "--max-trials must be at least 1."
    if args.max_replans < -1:
        return "--max-replans must be -1 or greater."
    if args.max_observation_chars != 0 and args.max_observation_chars < 200:
        return "--max-observation-chars must be 0 (disabled) or at least 200."
    if args.context_token_budget < 0:
        return "--context-token-budget must be 0 (disabled) or greater."
    if args.llm_max_retries < 0:
        return "--llm-max-retries must be 0 or greater."
    if args.circuit_breaker_threshold < 2:
        return "--circuit-breaker-threshold must be at least 2."
    if args.circuit_breaker_cooldown < 1:
        return "--circuit-breaker-cooldown must be at least 1."
    if args.enable_reflexion and (
        getattr(args, "checkpoint", None) or getattr(args, "resume", None)
    ):
        return "--checkpoint/--resume 暂不支持与 --enable-reflexion 同时使用。"
    if (
        args.enable_repeated_failure_policy_experiment
        and not args.enable_adaptive_replanning
        and not args.enable_evolution
    ):
        return (
            "--enable-repeated-failure-policy-experiment requires "
            "--enable-adaptive-replanning or --enable-evolution."
        )
    return ""


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
        "--max-observation-chars",
        type=int,
        default=saved_config.get("max_observation_chars", 8000),
        help="单条工具观察的字符上限，超出部分截断并附分页提示；0 表示不截断（默认：8000）。",
    )
    parser.add_argument(
        "--context-token-budget",
        type=int,
        default=saved_config.get("context_token_budget", 24000),
        help="对话历史的估算 token 预算，超限提前触发本地压缩；0 表示只按消息节奏压缩（默认：24000）。",
    )
    parser.add_argument(
        "--disable-edit-guard",
        dest="enable_edit_guard",
        action="store_false",
        default=saved_config.get("enable_edit_guard", True),
        help="关闭 read-before-edit 守卫（默认开启：edit_file 前必须读过目标文件，写后需重读）。",
    )
    parser.add_argument(
        "--llm-max-retries",
        type=int,
        default=saved_config.get("llm_max_retries", 2),
        help="LLM 瞬时故障（超时/断连/429/5xx）的统一重试次数；0 表示不重试（默认：2）。",
    )
    parser.add_argument(
        "--enable-reflexion",
        action="store_true",
        default=saved_config.get("enable_reflexion", False),
        help="启用失败后的 Reflexion 反思重试。默认关闭。",
    )
    parser.add_argument(
        "--max-trials",
        type=int,
        default=saved_config.get("max_trials", 3),
        help="启用 Reflexion 时最多尝试的轮数（默认：3）。",
    )
    parser.add_argument(
        "--enable-critic",
        action="store_true",
        default=saved_config.get("enable_critic", False),
        help="启用完成前 Critic 审查门禁。默认关闭。",
    )
    parser.add_argument(
        "--enable-adaptive-replanning",
        action="store_true",
        default=saved_config.get("enable_adaptive_replanning", False),
        help="启用基于失败信号的自适应重规划。默认关闭。",
    )
    parser.add_argument(
        "--max-replans",
        type=int,
        default=saved_config.get("max_replans", -1),
        help="自适应重规划最多触发次数；-1 表示不限（默认：-1）。",
    )
    parser.add_argument(
        "--enable-repeated-failure-policy-experiment",
        action="store_true",
        default=saved_config.get("enable_repeated_failure_policy_experiment", False),
        help="启用重复失败时的实验性跳出策略。默认关闭。",
    )
    parser.add_argument(
        "--enable-evolution",
        action="store_true",
        default=saved_config.get("enable_evolution", False),
        help="启用实验性进化恢复模式：自动打开自适应重规划和重复失败跳出策略。默认关闭。",
    )
    parser.add_argument(
        "--enable-memory-hygiene",
        action="store_true",
        default=saved_config.get("enable_memory_hygiene", False),
        help="启用记忆卫生：成功后降权相关失败记忆，并把召回锚定到任务原文。默认关闭。",
    )
    parser.add_argument(
        "--enable-llm-compression",
        action="store_true",
        default=saved_config.get("enable_llm_compression", False),
        help="启用 LLM 摘要压缩：折叠旧上下文时额外生成一条摘要记忆（消耗模型调用）。默认关闭。",
    )
    parser.add_argument(
        "--enable-circuit-breaker",
        action="store_true",
        default=saved_config.get("enable_circuit_breaker", False),
        help="启用工具熔断：同一工具同类错误连续失败达到阈值后临时禁用并引导换路。默认关闭。",
    )
    parser.add_argument(
        "--circuit-breaker-threshold",
        type=int,
        default=saved_config.get("circuit_breaker_threshold", 3),
        help="触发熔断所需的连续失败次数（默认：3，最小 2）。",
    )
    parser.add_argument(
        "--circuit-breaker-cooldown",
        type=int,
        default=saved_config.get("circuit_breaker_cooldown", 5),
        help="熔断后允许探针重试前的冷却步数（默认：5，最小 1）。",
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
        "--checkpoint",
        type=Path,
        help="每步结束后把 run 状态原子写入该 JSON 文件，用于崩溃后 --resume 续跑。",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help="从 --checkpoint 生成的文件恢复运行；任务参数可省略（取 checkpoint 内任务）。",
    )
    parser.add_argument(
        "--reflexion-memory-file",
        default=saved_config.get("reflexion_memory_file", ""),
        help="Reflexion 经验教训的持久化文件（可选）；启动时加载，结束时保存。",
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
