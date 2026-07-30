"""``dm-agent-web`` 入口：解析参数、生成 token、起 uvicorn。

默认姿势是**最保守的那一档**：只绑 127.0.0.1、生成一次性 token、
不开写权限（``--read-only`` 之外的写操作要等阶段 3 的运行能力接进来）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .settings import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ServerSettings,
    generate_token,
    is_loopback_host,
)

# 缺 [web] extra 时给一条能直接照着敲的修复命令，而不是丢一个 ImportError traceback。
_MISSING_DEPS = (
    "缺少 Web 控制台依赖。请执行：\n"
    "  uv sync --frozen --extra dev        # 开发环境\n"
    "  pip install 'dm-code-agent[web]'    # 或者直接装 extra"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dm-agent-web",
        description="DM-Code-Agent Web 控制台：会话审计 + 运行工作台。",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"监听地址（默认 {DEFAULT_HOST}）。非 loopback 地址强制要求 token。",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"监听端口（默认 {DEFAULT_PORT}）"
    )
    parser.add_argument(
        "--sessions-dir",
        default="sessions",
        help="会话 JSONL 所在目录（默认 ./sessions）",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="agent 的工作目录，运行时在这里读写文件（默认当前目录）",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="只提供审计能力，禁用一切写操作（发起运行、分叉会话）。公开展厅用这个。",
    )
    parser.add_argument(
        "--token",
        default="",
        help="固定访问 token；省略时自动生成一个一次性 token 并打印在启动地址里。",
    )
    parser.add_argument(
        "--no-token",
        action="store_true",
        help="关闭 token 校验。只在 loopback 上允许，且不推荐。",
    )
    parser.add_argument(
        "--static-dir",
        default="",
        help="前端产物目录；省略时用随包分发的 dm_agent/server/static。",
    )
    parser.add_argument("--reload", action="store_true", help="代码变更自动重载（开发用）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])

    if args.no_token and not is_loopback_host(args.host):
        print("[ERR] --no-token 只能用于 loopback 地址。", file=sys.stderr)
        return 2
    if args.no_token and args.token:
        print("[ERR] --no-token 与 --token 互斥。", file=sys.stderr)
        return 2

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # pragma: no cover - dotenv 是核心依赖，正常装不上才会走到
        pass

    token = "" if args.no_token else (args.token or generate_token())
    try:
        settings = ServerSettings(
            sessions_dir=Path(args.sessions_dir),
            workspace=Path(args.workspace),
            host=args.host,
            port=args.port,
            token=token,
            read_only=args.read_only,
            static_dir=Path(args.static_dir) if args.static_dir else None,
        )
    except ValueError as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 2

    try:
        import uvicorn

        from .app import create_app
    except ImportError:
        print(f"[ERR] {_MISSING_DEPS}", file=sys.stderr)
        return 3

    settings.sessions_dir.mkdir(parents=True, exist_ok=True)
    _print_banner(settings)

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
        # 每条 SSE 事件都要立刻到达浏览器，不能被访问日志的缓冲拖住。
        access_log=False,
    )
    return 0


def _print_banner(settings: ServerSettings) -> None:
    mode = "只读展厅" if settings.read_only else "完整工作台"
    auth = "token 已启用" if settings.auth_required else "！未启用 token"
    print("DM-Code-Agent Web Console")
    print(f"  模式      {mode}")
    print(f"  鉴权      {auth}")
    print(f"  workspace {settings.workspace}")
    print(f"  sessions  {settings.sessions_dir}")
    print(f"  打开      {settings.public_url()}")
    if not settings.read_only:
        print("  提示      非只读模式下，agent 会在上面的 workspace 里真实读写文件。")
