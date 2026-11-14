"""服务生命周期负责回收没有浏览器连接的空闲对话。"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

from dm_agent.server.process import RunProcess
from dm_agent.server.runs import RunRecord, RunRegistry, _count_run_ends, _read_agent_status


def test_idle_conversation_is_reaped_without_http_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from dm_agent.server.app import _lifespan, create_app
    from dm_agent.server.settings import ServerSettings

    monkeypatch.setattr("dm_agent.server.app.IDLE_REAP_INTERVAL_SECONDS", 0.01)
    app = create_app(ServerSettings(sessions_dir=tmp_path))
    registry = RunRegistry(idle_timeout=1.0)
    app.state.registry = registry
    process = RunProcess(
        [sys.executable, "-c", "import sys; sys.stdin.read()"],
        cwd=tmp_path,
        trace_path=tmp_path / "idle.jsonl",
    )
    process.start(stdin_pipe=True)
    record = RunRecord(
        run_id="idle",
        task="",
        session_name="idle.jsonl",
        trace_path=process.trace_path,
        process=process,
        kind="conversation",
        last_activity=time.time() - 10,
    )
    registry._records[record.run_id] = record

    async def run() -> None:
        async with _lifespan(app):
            # 只等子进程，期间不请求 API 或手动调用 reap_idle。
            assert await asyncio.to_thread(process.wait, 5.0) == 0

    try:
        asyncio.run(run())
    finally:
        process.stop(grace_seconds=1.0)


def test_run_status_scan_skips_invalid_entries(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_bytes(
        b'{"bad":"\xff"}\n'
        b"null\n"
        b'{"event":"run_end","payload":{"status":"success"}}\n'
        b'{"event":"run_end","payload":"broken"}\n'
    )
    assert _count_run_ends(path) == 2
    assert _read_agent_status(path) == "success"
