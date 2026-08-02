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

__all__ = ["ConversationTurn", "RunRecord", "RunRegistry"]

# 同时在跑的运行数上限。每个运行都是一个真在读写你工作区的 agent，
# 并发跑多个几乎一定互相踩；留 2 是为了「跑一个、再开一个对照」这种用法。
MAX_CONCURRENT_RUNS = 2

# 对话子进程空闲多久后回收。长驻进程是这次改造引入的**唯一**新资源泄漏面：
# 用户开了对话就关掉浏览器，进程会一直挂着（还占着 MCP 服务器）。
CONVERSATION_IDLE_TIMEOUT_SECONDS = 30 * 60


@dataclass
class ConversationTurn:
    """对话里的一轮。

    刻意**不记「这轮结束了没有」**——那个真相在会话日志里（本轮的 ``run_end``），
    由 ``RunRecord.completed_turns`` 现读现算。内存里再存一份就会有两个事实来源。
    """

    index: int
    task: str
    submitted_at: float = field(default_factory=time.time)

    def to_payload(self) -> dict[str, Any]:
        return {"index": self.index, "task": self.task, "submitted_at": self.submitted_at}


@dataclass
class RunRecord:
    """一次运行的服务端视图。

    ``kind="conversation"`` 时这条记录代表一个**长驻**子进程：它一直活着等下一轮任务
    从 stdin 进来，因此 ``is_running`` 的含义是「对话还开着」，不是「某一轮还在跑」。
    某一轮在不在跑看 ``is_busy``。
    """

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
    kind: str = "run"
    turns: list[ConversationTurn] = field(default_factory=list)
    last_activity: float = field(default_factory=time.time)

    @property
    def is_running(self) -> bool:
        return self.finished_at is None

    @property
    def completed_turns(self) -> int:
        """已经跑完的轮数 = 会话日志里 ``run_end`` 的条数。

        不在内存里维护这个计数：日志才是真相源，而且控制台随时可能在两轮之间重启。
        """
        return _count_run_ends(self.trace_path)

    @property
    def is_busy(self) -> bool:
        """当前有没有一轮正在跑。"""
        return self.is_running and self.completed_turns < len(self.turns)

    def idle_seconds(self, now: float | None = None) -> float:
        return max(0.0, (now if now is not None else time.time()) - self.last_activity)

    def status(self) -> str:
        """控制台展示用的状态。

        **不能只看退出码**：`dm-agent` 对 ``max_steps_exceeded`` 也返回 0——那不算
        CLI 失败，只是 agent 没做完。真相在会话日志的 ``run_end.status`` 里。
        端到端实测时就撞上过这个：CLI 说 max_steps_exceeded，控制台却报 completed。
        """
        if self.is_running:
            if self.kind == "conversation":
                return "running" if self.is_busy else "idle"
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
        payload: dict[str, Any] = {
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
            "kind": self.kind,
        }
        if self.kind == "conversation":
            payload.update(
                {
                    "turns": [turn.to_payload() for turn in self.turns],
                    "submitted_turns": len(self.turns),
                    "completed_turns": self.completed_turns,
                    "busy": self.is_busy,
                    "last_activity": self.last_activity,
                }
            )
        return payload


class RunRegistry:
    """run_id → RunRecord。

    uvicorn 的线程池会并发调用这些方法（同步的路由处理器跑在 worker 线程里），
    所以所有读写都在同一把锁下。
    """

    def __init__(
        self,
        *,
        max_concurrent: int = MAX_CONCURRENT_RUNS,
        idle_timeout: float = CONVERSATION_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self._records: dict[str, RunRecord] = {}
        self._lock = threading.Lock()
        self._max_concurrent = max_concurrent
        self._idle_timeout = idle_timeout

    def new_run_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for record in self._records.values() if self._refresh(record).is_running)

    def at_capacity(self) -> bool:
        """并发上限对一次性运行与对话一视同仁——它们都是在同一个工作区里干活的 agent。"""
        self.reap_idle()
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

    def submit_turn(self, run_id: str, task: str) -> ConversationTurn | None:
        """给一个对话追加一轮。会话已结束或上一轮还没跑完时返回 None。

        「上一轮跑完没有」查的是会话日志里的 ``run_end`` 条数，而不是内存标志位——
        这样即使控制台在两轮之间重启过，判断依然正确。
        """
        with self._lock:
            record = self._records.get(run_id)
            if record is None or record.kind != "conversation":
                return None
            self._refresh(record)
            if not record.is_running or record.is_busy:
                return None
            turn = ConversationTurn(index=len(record.turns) + 1, task=task)
            if not record.process.send_line({"task": task}):
                return None
            record.turns.append(turn)
            record.last_activity = time.time()
            if not record.task:
                # 首轮任务顺带成为这次对话的标题。
                record.task = task
            return turn

    def cancel(self, run_id: str) -> bool:
        """终止一个在跑的运行。已结束的返回 False。

        对话走优雅路径（先关 stdin 让 agent 收尾），一次性运行直接终止。
        """
        with self._lock:
            record = self._records.get(run_id)
            if record is None or not self._refresh(record).is_running:
                return False
            kind = record.kind
        # 终止会阻塞几秒（先 CTRL_BREAK / SIGTERM 再硬杀），放在锁外做，
        # 否则期间所有状态查询都会被卡住。
        stopped = record.process.shutdown() if kind == "conversation" else record.process.stop()
        with self._lock:
            record.cancelled = True
            self._refresh(record)
        return stopped

    def reap_idle(self, now: float | None = None) -> tuple[str, ...]:
        """收掉闲置太久的对话进程，返回被收掉的 run_id。

        长驻进程是这次改造唯一新增的资源泄漏面：用户开了对话直接关浏览器，
        子进程会一直挂着（还占着它拉起的 MCP 服务器）。没有这个回收器就等于漏。

        返回元组而不是列表：这里的 ``list`` 在类作用域被同名方法遮住了，而这个返回值
        本来就只是一份「刚刚收掉了谁」的只读报告。
        """
        if self._idle_timeout <= 0:
            return ()
        moment = now if now is not None else time.time()
        with self._lock:
            stale = [
                record
                for record in self._records.values()
                if record.kind == "conversation"
                and self._refresh(record).is_running
                and not record.is_busy
                and record.idle_seconds(moment) >= self._idle_timeout
            ]
        reaped = []
        for record in stale:
            record.process.shutdown(grace_seconds=2.0)
            with self._lock:
                self._refresh(record)
            reaped.append(record.run_id)
        return tuple(reaped)

    def stop_all(self) -> None:
        """进程退出时的清理：把还在跑的都收掉，不留孤儿。"""
        for record in self.list():
            if record.is_running:
                if record.kind == "conversation":
                    record.process.shutdown(grace_seconds=1.0)
                else:
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
            elif record.kind == "conversation" and record.is_busy:
                # 正在跑的一轮就是活动本身。不刷新的话，一轮跑了超过 idle_timeout
                # 之后一结束就会被立刻回收。
                record.last_activity = time.time()
        return record


def _count_run_ends(trace_path: Path) -> int:
    """数会话日志里有几条 ``run_end``，即已经跑完了几轮。

    会话日志是 **append-only** 的，所以这里做增量扫描：只读上次之后新增的字节，
    并把结尾的半行留到下次（写侧是「整行 + flush」，但读侧仍可能撞上写一半的行）。
    每次状态查询都全文重扫会让长会话越跑越慢。
    """
    key = str(trace_path)
    offset, count = _RUN_END_SCAN.get(key, (0, 0))
    try:
        size = trace_path.stat().st_size
    except OSError:
        return count
    if size < offset:
        # 文件被替换或截断（正常流程不会发生）。丢掉缓存重来。
        offset, count = 0, 0
    if size == offset:
        return count
    try:
        with trace_path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
    except OSError:
        return count

    last_newline = data.rfind(b"\n")
    if last_newline < 0:
        return count  # 还没有完整的一行
    complete, consumed = data[: last_newline + 1], last_newline + 1
    for raw_line in complete.split(b"\n"):
        text = raw_line.strip()
        if not text.startswith(b"{"):
            continue
        try:
            entry = json.loads(text)
        except json.JSONDecodeError:
            continue
        if entry.get("event") == "run_end":
            count += 1
    _RUN_END_SCAN[key] = (offset + consumed, count)
    return count


# path → (已扫描到的字节偏移, 已数到的 run_end 条数)。append-only 让增量扫描成立。
_RUN_END_SCAN: dict[str, tuple[int, int]] = {}


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
