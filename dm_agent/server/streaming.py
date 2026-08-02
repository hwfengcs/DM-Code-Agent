"""JSONL tail → SSE。

实时流的数据源就是会话日志本身，不是内存里另一条旁路——``TraceWriter.record()``
每条都 ``flush()``，所以边写边读拿到的与事后 ``dm-agent-trace view`` 读到的是
**同一份字节**。这条设计让「实时看」和「事后审计」不可能出现口径差异。

三个必须处理对的细节：

1. **断点续传**：SSE 的 ``id:`` 用条目在文件里的行号（0 起）。会话日志 append-only，
   行号永不变动，所以浏览器断线重连时带上的 ``Last-Event-ID: N`` 可以直接翻译成
   「从第 N+1 行接着发」。
2. **半行**：写侧是「整行 + flush」，但读侧仍可能撞上写到一半的行。只有以 ``\\n``
   结尾的完整行才发出去，残段留在缓冲里等下一轮——否则会给前端一个解析不了的 JSON。
3. **心跳**：长时间没有新条目时发 SSE 注释行，免得中间的代理把空闲连接掐掉。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

__all__ = ["parse_last_event_id", "sse_message", "stream_session_lines"]

# 轮询间隔。会话日志是本地文件，0.25s 足够跟手，也不至于把 CPU 转满。
POLL_INTERVAL_SECONDS = 0.25
# 心跳间隔。低于常见代理的 60s 空闲超时。
HEARTBEAT_SECONDS = 15.0
# 文件迟迟不出现时的等待上限（子进程要 1–2s 才建出 trace 文件）。
WAIT_FOR_FILE_SECONDS = 30.0


def sse_message(*, event: str, data: Any, event_id: int | None = None) -> str:
    """拼一条 SSE 消息。

    ``data`` 一律序列化成单行 JSON——SSE 用换行分隔字段，多行 payload 会破坏协议。
    """
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def parse_last_event_id(raw: str | None) -> int:
    """把 ``Last-Event-ID`` 头解析成已收到的行数。

    解析不了就从头开始重发——重复一遍好过静默丢事件。
    """
    if not raw:
        return -1
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return -1
    return value if value >= 0 else -1


async def stream_session_lines(
    path: Path,
    *,
    start_after: int = -1,
    is_finished: Callable[[], bool],
    finish_payload: Callable[[], dict[str, Any]],
) -> AsyncIterator[str]:
    """跟读 ``path``，把每条 JSONL 条目作为一条 SSE 事件产出。

    Args:
        path: 会话日志路径，可能还不存在。
        start_after: 已经发过的最后一行行号；``-1`` 表示从头发。
        is_finished: 返回 True 表示子进程已结束（由 ``RunRegistry`` 提供）。
        finish_payload: 结束时附带的终态信息。

    产出顺序保证：全部条目 → 一条 ``done``。子进程结束后仍会把文件读干净，
    避免最后几条（尤其是 ``run_end``）丢掉。
    """
    line_index = -1
    buffer = b""
    offset = 0
    last_heartbeat = asyncio.get_running_loop().time()
    waited_for_file = 0.0

    while True:
        loop_time = asyncio.get_running_loop().time()
        exists = path.is_file()

        if not exists:
            # 子进程还没建出文件。它已经结束却仍没有文件 = 起都没起来。
            if is_finished():
                yield sse_message(event="done", data=finish_payload())
                return
            waited_for_file += POLL_INTERVAL_SECONDS
            if waited_for_file >= WAIT_FOR_FILE_SECONDS:
                yield sse_message(
                    event="error",
                    data={"message": f"等待 {WAIT_FOR_FILE_SECONDS:.0f}s 仍未生成会话日志。"},
                )
                return
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue

        chunk, offset = _read_from(path, offset)
        if chunk:
            buffer += chunk
            # 最后一段若不以换行结尾就是半行，留到下一轮。
            *complete, buffer = buffer.split(b"\n")
            for raw_line in complete:
                line_index += 1
                if line_index <= start_after:
                    continue  # 续传：这些行客户端已经有了
                text = raw_line.strip()
                if not text:
                    continue
                try:
                    entry = json.loads(text)
                except json.JSONDecodeError:
                    # 单条坏行不该终止整个流；标出来让前端能显示。
                    yield sse_message(
                        event="malformed",
                        data={"line": line_index},
                        event_id=line_index,
                    )
                    continue
                yield sse_message(event="entry", data=entry, event_id=line_index)
                last_heartbeat = loop_time
            continue  # 可能还有更多数据，先不睡

        # 没有新数据。子进程结束了就再确认一次文件已读干净，然后收尾。
        if is_finished():
            trailing, offset = _read_from(path, offset)
            if trailing:
                buffer += trailing
                continue
            if buffer.strip():
                # 收尾时仍有残段：写侧被中断在半行，把它作为坏行报出去。
                line_index += 1
                yield sse_message(event="malformed", data={"line": line_index}, event_id=line_index)
            yield sse_message(event="done", data=finish_payload())
            return

        if loop_time - last_heartbeat >= HEARTBEAT_SECONDS:
            # SSE 注释行：客户端会忽略，但足以让中间代理认为连接还活着。
            yield ": keep-alive\n\n"
            last_heartbeat = loop_time

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def _read_from(path: Path, offset: int) -> tuple[bytes, int]:
    """从 ``offset`` 起读出新增字节，返回 ``(数据, 新 offset)``。

    以二进制读并自己切行，而不是按文本行迭代：文本模式下的换行转换会让
    offset 与真实字节数不一致，续传就会错位。
    """
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
            return data, offset + len(data)
    except OSError:
        # 文件可能正被替换或短暂锁住（Windows 上尤其常见）。下一轮再试。
        return b"", offset
