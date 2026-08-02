"""``dm-agent-web`` 入口：解析参数、生成 token、起 uvicorn。

默认姿势是**最保守的那一档**：只绑 127.0.0.1、生成一次性 token、
不开写权限（``--read-only`` 之外的写操作要等阶段 3 的运行能力接进来）。
"""

from __future__ import annotations

import argparse
import contextlib
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


def _configure_output_encoding() -> None:
    """让横幅里的中文在重定向到文件/管道时也不乱码。

    Windows 上 stdout 重定向后默认用系统 ANSI 代码页（简中环境是 cp936），
    横幅里的中文会变成一片问号。这里显式切到 UTF-8，并保留 ``errors="replace"``
    兜底——编码问题绝不能让服务起不来。

    刻意不复用 ``dm_agent.cli.ui.configure_console_encoding``：server 层不得依赖 cli
    （见 ``tests/test_server_layering.py``），而且那个函数只设 errors、不设 encoding。
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configure_output_encoding()
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])

    if args.no_token and not is_loopback_host(args.host):
        print("[ERR] --no-token 只能用于 loopback 地址。", file=sys.stderr)
        return 2
    if args.no_token and args.token:
        print("[ERR] --no-token 与 --token 互斥。", file=sys.stderr)
        return 2

    try:
        from dm_agent.paths import load_env_files

        # 与 CLI 同一套查找顺序：./.env → ~/.dm_agent/.env。子进程各自也会再加载一次，
        # 但 server 进程自己也要能读到 key（例如将来做启动前的可用性检查）。
        load_env_files()
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
    """打印启动信息。

    ``flush=True`` 不是可选的：stdout 被重定向到管道或文件时是块缓冲的，而
    ``uvicorn.run()`` 之后进程就一直不退出，缓冲区永远不会被刷出去——用户最需要的
    那条带 token 的地址就此消失（uvicorn 自己的日志走 stderr，所以看起来只是
    「横幅没了」，很难联想到缓冲）。
    """
    mode = "只读展厅" if settings.read_only else "完整工作台"
    auth = "token 已启用" if settings.auth_required else "！未启用 token"
    lines = [
        "DM-Code-Agent Web Console",
        f"  模式      {mode}",
        f"  鉴权      {auth}",
        f"  workspace {settings.workspace}",
        f"  sessions  {settings.sessions_dir}",
        f"  打开      {settings.public_url()}",
    ]
    if not settings.read_only:
        lines.append("  提示      非只读模式下，agent 会在上面的 workspace 里真实读写文件。")
    print("\n".join(lines), flush=True)
