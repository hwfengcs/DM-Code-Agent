"""命令行参数定义与校验。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .config import load_config_from_file


def validate_feature_args(args: argparse.Namespace) -> str:
    """Validate default-off advanced feature CLI arguments."""
    if args.max_replans < -1:
        return "--max-replans must be -1 or greater."
    if args.max_observation_chars != 0 and args.max_observation_chars < 200:
        return "--max-observation-chars must be 0 (disabled) or at least 200."
    if args.context_token_budget < 0:
        return "--context-token-budget must be 0 (disabled) or greater."
    if args.llm_max_retries < 0:
        return "--llm-max-retries must be 0 or greater."
    if getattr(args, "resume_at", "") and not getattr(args, "resume", None):
        return "--resume-at 需要与 --resume 一起使用。"
    conversation_error = _validate_conversation_args(args)
    if conversation_error:
        return conversation_error
    checkpoint_path = getattr(args, "checkpoint", None)
    trace_path = getattr(args, "trace", None)
    if checkpoint_path and trace_path and Path(checkpoint_path) == Path(trace_path):
        # checkpoint 里有完整对话（含模型原始输出），trace 默认是可分享的脱敏档。
        # 指向同一个文件会让脱敏档被完整历史悄悄污染，直接拒绝。
        return "--trace 与 --checkpoint 不能指向同一个文件（前者默认脱敏，后者含完整对话）。"
    return ""


def _validate_conversation_args(args: argparse.Namespace) -> str:
    """校验 ``--conversation-stdin`` 的四条前置条件。

    这个模式让一个进程用**同一个** ``ReactAgent`` 顺序跑多轮，因此凡是会重置或
    分叉对话历史的开关都与它语义冲突，宁可直接拒绝也不要跑出一个「看起来是多轮、
    实际上历史被悄悄清掉」的会话。
    """
    if not getattr(args, "conversation_stdin", False):
        return ""
    if getattr(args, "task", None):
        return "--conversation-stdin 从 stdin 读取任务，不能同时给位置参数任务。"
    if not getattr(args, "trace", None):
        # 会话日志是控制台/调用方读取进展的唯一通道（子进程 stdout 只是人类可读日志）。
        return "--conversation-stdin 必须配合 --trace，否则没有任何地方能读到每一轮的进展。"
    if getattr(args, "resume", None) or getattr(args, "resume_at", ""):
        return "--conversation-stdin 不支持 --resume：resume 恢复的是同一任务的中断点。"
    return ""


def parse_args(argv: Any) -> argparse.Namespace:
    # 先加载配置文件中的默认值
    saved_config = load_config_from_file()

    parser = argparse.ArgumentParser(description="运行基于 LLM 的 ReAct 智能体来完成任务描述。")
    parser.add_argument("task", nargs="?", help="智能体要完成的自然语言任务。")

    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        help="API 密钥（默认使用环境变量）。",
    )
    parser.add_argument(
        "--provider",
        default=saved_config.get("provider", "deepseek"),
        help="已注册的 LLM 提供商（内置 deepseek/openai/claude/gemini，默认：deepseek）。",
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
        help=(
            "关闭 read-before-edit 守卫（默认开启：首次 edit_file 前必须读过目标文件；"
            "依赖行号的连续编辑在写后需重读）。"
        ),
    )
    parser.add_argument(
        "--llm-max-retries",
        type=int,
        default=saved_config.get("llm_max_retries", 2),
        help="LLM 瞬时故障（超时/断连/429/5xx）的统一重试次数；0 表示不重试（默认：2）。",
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
        "--interactive",
        action="store_true",
        help="启动交互式菜单模式。",
    )
    parser.add_argument(
        "--conversation-stdin",
        dest="conversation_stdin",
        action="store_true",
        help=(
            '长驻会话模式：从 stdin 按 JSON Lines 读取任务（每行 {"task": "..."}），'
            "用同一个 agent 顺序执行多轮并共享对话历史；读到 EOF 退出。必须配合 --trace。"
        ),
    )
    extension_group = parser.add_mutually_exclusive_group()
    extension_group.add_argument(
        "--no-extensions",
        action="store_true",
        help="关闭 entry point、用户目录、项目目录及显式文件扩展；内置能力仍保留。",
    )
    extension_group.add_argument(
        "--extension",
        dest="extension_paths",
        action="append",
        type=Path,
        default=[],
        metavar="PATH",
        help="仅本次显式加载一个可信 .py 扩展；可重复指定。",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        help="将本次任务的结构化执行轨迹写入 JSONL 文件。",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help=(
            "每步结束后落一份 run 状态，用于崩溃后 --resume 续跑。"
            "*.jsonl 写成 append-only 会话日志（保留每一步的历史快照，可配合 "
            "--resume-at 与 dm-agent-trace fork）；其他后缀写成单文件 JSON 快照。"
        ),
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help="从 --checkpoint 生成的文件恢复运行；任务参数可省略（取 checkpoint 内任务）。",
    )
    parser.add_argument(
        "--resume-at",
        default="",
        metavar="ENTRY_ID",
        help="仅对 JSONL 会话日志有效：从该条目（或之前最近的 checkpoint 条目）恢复；支持唯一前缀。",
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
