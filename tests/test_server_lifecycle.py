"""服务生命周期负责回收没有浏览器连接的空闲对话。"""

from __future__ import annotations

import asyncio
import json
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


@pytest.mark.parametrize("separator", [" ", " ", "\x85"])
def test_run_status_is_read_from_an_entry_containing_unicode_line_separators(
    tmp_path: Path, separator: str
) -> None:
    """JSONL 的行界只有换行符。

    写入端用 ``ensure_ascii=False``，``final_answer`` 里的 U+2028 之类会原样落盘；按它们
    断行就读不到 ``run_end``，状态退回只看退出码，「步数耗尽」会被报成 completed。
    """
    path = tmp_path / "run.jsonl"
    entry = {
        "event": "run_end",
        "payload": {"status": "max_steps_exceeded", "final_answer": f"第一段{separator}第二段"},
    }
    path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")

    assert _read_agent_status(path) == "max_steps_exceeded"
    assert _count_run_ends(path) == 1


def test_reaper_survives_a_failing_sweep_and_shutdown_still_stops_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """一次回收失败既不能让回收器就此停摆，也不能让关停跳过 ``stop_all``。"""
    pytest.importorskip("fastapi")
    from dm_agent.server.app import _lifespan, create_app
    from dm_agent.server.settings import ServerSettings

    class FlakyRegistry(RunRegistry):
        def __init__(self) -> None:
            super().__init__()
            self.sweeps = 0
            self.stopped = False

        def reap_idle(self, now: float | None = None) -> tuple[str, ...]:
            self.sweeps += 1
            raise RuntimeError("injected sweep failure")

        def stop_all(self) -> None:
            self.stopped = True

    monkeypatch.setattr("dm_agent.server.app.IDLE_REAP_INTERVAL_SECONDS", 0.01)
    app = create_app(ServerSettings(sessions_dir=tmp_path))
    registry = FlakyRegistry()
    app.state.registry = registry

    async def run() -> None:
        async with _lifespan(app):
            deadline = time.time() + 5.0
            while registry.sweeps < 2 and time.time() < deadline:
                await asyncio.sleep(0.01)

    asyncio.run(run())

    assert registry.sweeps >= 2, "第一次失败之后回收器就不再运行了"
    assert registry.stopped, "关停没有走到 stop_all"
