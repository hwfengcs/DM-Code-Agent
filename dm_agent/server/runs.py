"""在跑的运行的内存注册表。

刻意**不持久化**：控制台重启后正在跑的子进程就成了孤儿，与其假装还能管它们，不如
让状态跟着进程生命周期走。已完成运行的全部信息都在会话 JSONL 里，那才是真相源——
注册表只是「哪些进程还活着」这一瞬时状态的索引。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .process import RunProcess

__all__ = ["RunRecord", "RunRegistry"]

# 同时在跑的运行数上限。每个运行都是一个真在读写你工作区的 agent，
# 并发跑多个几乎一定互相踩；留 2 是为了「跑一个、再开一个对照」这种用法。
MAX_CONCURRENT_RUNS = 2


@dataclass
class RunRecord:
    """一次运行的服务端视图。"""

    run_id: str
    task: str
    session_name: str
    trace_path: Path
    process: RunProcess
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    exit_code: int | None = None
    cancelled: bool = False
    error: str = ""
    # 会话日志 run_end 里的 agent 状态（success / max_steps_exceeded / ...）。
    agent_status: str = ""

    @property
    def is_running(self) -> bool:
        return self.finished_at is None

    def status(self) -> str:
        """控制台展示用的状态。

        **不能只看退出码**：`dm-agent` 对 ``max_steps_exceeded`` 也返回 0——那不算
        CLI 失败，只是 agent 没做完。真相在会话日志的 ``run_end.status`` 里。
        端到端实测时就撞上过这个：CLI 说 max_steps_exceeded，控制台却报 completed。
        """
        if self.is_running:
            return "running"
        if self.cancelled:
            return "cancelled"
        if self.exit_code != 0:
            return "failed"
        # 进程正常退出，但 agent 自己没宣布成功（步数耗尽、被完成门否决等）。
        if self.agent_status and self.agent_status != "success":
            return "incomplete"
        return "completed"

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "session": self.session_name,
            "status": self.status(),
            "agent_status": self.agent_status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "cancelled": self.cancelled,
            "error": self.error,
            "pid": self.process.pid,
        }


class RunRegistry:
    """run_id → RunRecord。

    uvicorn 的线程池会并发调用这些方法（同步的路由处理器跑在 worker 线程里），
    所以所有读写都在同一把锁下。
    """

    def __init__(self, *, max_concurrent: int = MAX_CONCURRENT_RUNS) -> None:
        self._records: dict[str, RunRecord] = {}
        self._lock = threading.Lock()
        self._max_concurrent = max_concurrent

    def new_run_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for record in self._records.values() if self._refresh(record).is_running)

    def at_capacity(self) -> bool:
        return self.running_count() >= self._max_concurrent

    def register(self, record: RunRecord) -> None:
        with self._lock:
            self._records[record.run_id] = record

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            record = self._records.get(run_id)
            return self._refresh(record) if record else None

    def list(self) -> list[RunRecord]:
        with self._lock:
            records = [self._refresh(record) for record in self._records.values()]
        return sorted(records, key=lambda record: record.started_at, reverse=True)

    def cancel(self, run_id: str) -> bool:
        """终止一个在跑的运行。已结束的返回 False。"""
        with self._lock:
            record = self._records.get(run_id)
            if record is None or not self._refresh(record).is_running:
                return False
        # 终止会阻塞几秒（先 CTRL_BREAK / SIGTERM 再硬杀），放在锁外做，
        # 否则期间所有状态查询都会被卡住。
        stopped = record.process.stop()
        with self._lock:
            record.cancelled = True
            self._refresh(record)
        return stopped

    def stop_all(self) -> None:
        """进程退出时的清理：把还在跑的都收掉，不留孤儿。"""
        for record in self.list():
            if record.is_running:
                record.process.stop(grace_seconds=1.0)

    def _refresh(self, record: RunRecord) -> RunRecord:
        """按子进程的真实状态更新记录。调用方必须已持锁。"""
        if record.finished_at is None:
            code = record.process.poll()
            if code is not None:
                record.exit_code = code
                record.finished_at = time.time()
                record.agent_status = _read_agent_status(record.trace_path)
                if code != 0 and not record.error:
                    record.error = record.process.read_output()
        return record


def _read_agent_status(trace_path: Path) -> str:
    """从会话日志的最后一条 ``run_end`` 里取 agent 自己判定的状态。

    只读最后若干行：会话日志可能很大，而 ``run_end`` 一定在末尾。读失败一律返回空串
    —— 拿不到 agent 状态时退回「只看退出码」的旧口径，绝不让它影响运行本身。
    """
    try:
        with trace_path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            window = min(size, 64 * 1024)
            handle.seek(size - window)
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""

    for line in reversed(tail.splitlines()):
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            entry = json.loads(text)
        except json.JSONDecodeError:
            continue
        if entry.get("event") == "run_end":
            payload = entry.get("payload") or {}
            status = payload.get("status")
            return str(status) if status else ""
    return ""
