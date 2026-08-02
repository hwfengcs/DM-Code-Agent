"""JSONL tail → SSE 的行为测试。

这些用例**边写边读**，因为实时流最容易出错的地方恰恰是并发时序：半行、断点续传、
子进程结束后残留条目的收尾。全部用 ``asyncio.run`` 驱动，不引入 pytest-asyncio。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dm_agent.server.streaming import (
    parse_last_event_id,
    sse_message,
    stream_session_lines,
)


def parse_sse(chunks: list[str]) -> list[dict[str, Any]]:
    """把原始 SSE 文本解析回 ``{id, event, data}`` 列表，心跳注释行跳过。"""
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        if chunk.startswith(":"):
            continue
        record: dict[str, Any] = {}
        for line in chunk.strip().split("\n"):
            key, _, value = line.partition(": ")
            if key == "id":
                record["id"] = int(value)
            elif key == "event":
                record["event"] = value
            elif key == "data":
                record["data"] = json.loads(value)
        if record:
            events.append(record)
    return events


def entry_line(index: int, event: str = "step") -> str:
    return (
        json.dumps(
            {
                "id": f"sess-{index:04d}",
                "parent_id": f"sess-{index - 1:04d}" if index else "",
                "timestamp": "2026-02-01T00:00:00+00:00",
                "run_id": "run-live",
                "event": event,
                "payload": {"step_number": index},
            },
            ensure_ascii=False,
        )
        + "\n"
    )


async def collect(
    path: Path,
    *,
    start_after: int = -1,
    writer: Callable[[], Any] | None = None,
    finished: list[bool] | None = None,
) -> list[dict[str, Any]]:
    """跑一遍流，可选地并发执行一个写入协程。"""
    flag = finished if finished is not None else [True]
    chunks: list[str] = []

    async def consume() -> None:
        async for chunk in stream_session_lines(
            path,
            start_after=start_after,
            is_finished=lambda: flag[0],
            finish_payload=lambda: {"status": "completed"},
        ):
            chunks.append(chunk)

    if writer is None:
        await consume()
    else:
        await asyncio.gather(consume(), writer())
    return parse_sse(chunks)


# --- SSE 编码 -----------------------------------------------------------


def test_sse_message_shape() -> None:
    rendered = sse_message(event="entry", data={"a": 1}, event_id=7)
    assert rendered == 'id: 7\nevent: entry\ndata: {"a": 1}\n\n'


def test_sse_data_is_always_single_line() -> None:
    """SSE 用换行分隔字段，多行 payload 会破坏协议。"""
    rendered = sse_message(event="entry", data={"text": "第一行\n第二行"})
    body = [line for line in rendered.strip().split("\n") if line.startswith("data: ")]
    assert len(body) == 1
    assert json.loads(body[0][len("data: ") :])["text"] == "第一行\n第二行"


def test_sse_keeps_chinese_readable() -> None:
    assert "任务" in sse_message(event="entry", data={"task": "任务"})


# --- 断点续传的 id 解析 -------------------------------------------------


def test_parse_last_event_id() -> None:
    assert parse_last_event_id(None) == -1
    assert parse_last_event_id("") == -1
    assert parse_last_event_id("0") == 0
    assert parse_last_event_id(" 12 ") == 12
    # 解析不了就从头重发——重复好过静默丢事件。
    assert parse_last_event_id("garbage") == -1
    assert parse_last_event_id("-5") == -1


# --- 静态文件（子进程已结束）-------------------------------------------


def test_streams_every_entry_then_done(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text("".join(entry_line(index) for index in range(3)), encoding="utf-8")

    events = asyncio.run(collect(path))
    assert [event["event"] for event in events] == ["entry", "entry", "entry", "done"]
    # id 就是行号，0 起。
    assert [event["id"] for event in events[:3]] == [0, 1, 2]
    assert events[0]["data"]["id"] == "sess-0000"
    assert events[-1]["data"]["status"] == "completed"


def test_resumption_skips_already_delivered_lines(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text("".join(entry_line(index) for index in range(5)), encoding="utf-8")

    events = asyncio.run(collect(path, start_after=2))
    entries = [event for event in events if event["event"] == "entry"]
    assert [event["id"] for event in entries] == [3, 4]


def test_resuming_past_the_end_yields_only_done(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text(entry_line(0), encoding="utf-8")
    events = asyncio.run(collect(path, start_after=99))
    assert [event["event"] for event in events] == ["done"]


def test_malformed_line_does_not_kill_the_stream(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text(entry_line(0) + "{not json\n" + entry_line(2), encoding="utf-8")

    events = asyncio.run(collect(path))
    assert [event["event"] for event in events] == ["entry", "malformed", "entry", "done"]
    assert events[1]["data"]["line"] == 1


def test_blank_lines_are_skipped_but_still_count_as_lines(tmp_path: Path) -> None:
    """行号必须与文件真实行号对齐，否则续传会错位。"""
    path = tmp_path / "run.jsonl"
    path.write_text(entry_line(0) + "\n" + entry_line(2), encoding="utf-8")

    events = asyncio.run(collect(path))
    entries = [event for event in events if event["event"] == "entry"]
    assert [event["id"] for event in entries] == [0, 2]


def test_missing_file_with_finished_process_yields_done(tmp_path: Path) -> None:
    """子进程结束了却没建出文件 = 起都没起来。不能永远挂着等。"""
    events = asyncio.run(collect(tmp_path / "never-created.jsonl"))
    assert [event["event"] for event in events] == ["done"]


def test_empty_file_yields_only_done(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text("", encoding="utf-8")
    assert [event["event"] for event in asyncio.run(collect(path))] == ["done"]


# --- 边写边读 -----------------------------------------------------------


def test_entries_arrive_while_the_process_is_still_running(tmp_path: Path) -> None:
    """核心场景：一边有进程在追加写，一边把新条目推给浏览器。"""
    path = tmp_path / "live.jsonl"
    path.write_text("", encoding="utf-8")
    finished = [False]

    async def writer() -> None:
        for index in range(4):
            await asyncio.sleep(0.05)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(entry_line(index))
                handle.flush()
        await asyncio.sleep(0.4)
        finished[0] = True

    events = asyncio.run(collect(path, writer=writer, finished=finished))
    entries = [event for event in events if event["event"] == "entry"]
    assert [event["id"] for event in entries] == [0, 1, 2, 3]
    assert events[-1]["event"] == "done"


def test_partial_line_is_not_emitted_until_it_is_complete(tmp_path: Path) -> None:
    """写侧虽然是「整行 + flush」，读侧仍可能撞上半行。

    半行绝不能发出去——前端会拿到解析不了的 JSON。这条用例故意把一行拆成两半写。
    """
    path = tmp_path / "live.jsonl"
    path.write_text("", encoding="utf-8")
    finished = [False]
    full = entry_line(0)
    cut = len(full) // 2

    async def writer() -> None:
        await asyncio.sleep(0.05)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(full[:cut])  # 前半行，无换行
            handle.flush()
        # 给读侧足够时间轮询到这个半行状态。
        await asyncio.sleep(0.4)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(full[cut:])  # 补齐后半行 + 换行
            handle.flush()
        await asyncio.sleep(0.4)
        finished[0] = True

    events = asyncio.run(collect(path, writer=writer, finished=finished))
    entries = [event for event in events if event["event"] == "entry"]
    # 恰好一条，且内容完整——不能出现半行被当成坏行发出去。
    assert len(entries) == 1
    assert entries[0]["data"]["id"] == "sess-0000"
    assert not [event for event in events if event["event"] == "malformed"]


def test_trailing_entries_are_flushed_after_process_exit(tmp_path: Path) -> None:
    """子进程结束的瞬间可能还有没读到的条目（尤其 run_end）。一条都不能丢。"""
    path = tmp_path / "live.jsonl"
    path.write_text("", encoding="utf-8")
    finished = [False]

    async def writer() -> None:
        await asyncio.sleep(0.05)
        # 先标记「进程已结束」，再把最后几条写进去，模拟最坏的时序。
        finished[0] = True
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry_line(0) + entry_line(1, event="run_end"))
            handle.flush()

    events = asyncio.run(collect(path, writer=writer, finished=finished))
    entries = [event for event in events if event["event"] == "entry"]
    assert len(entries) == 2
    assert entries[-1]["data"]["event"] == "run_end"
    assert events[-1]["event"] == "done"


def test_incomplete_trailing_line_at_exit_is_reported(tmp_path: Path) -> None:
    """进程被杀在半行上：把残段作为坏行报出去，而不是假装它不存在。"""
    path = tmp_path / "live.jsonl"
    path.write_text(entry_line(0) + '{"id": "sess-0001", "eve', encoding="utf-8")

    events = asyncio.run(collect(path))
    assert [event["event"] for event in events] == ["entry", "malformed", "done"]
