"""多轮对话端点的端到端测试。

用一个**读 stdin、按轮写 JSONL** 的桩子进程代替真 CLI——理由与 ``test_server_runs.py``
的 ``fake_agent`` 完全相同（那里记着「靠没配 key 让真 CLI 快速失败」曾经真的花钱的教训）。
桩进程让这些用例彻底离线，还能精确控制每一轮的节奏。

真 argv 与真 CLI 解析器的一致性由 ``test_server_process.py`` 单独保证；
「多轮真的共享对话历史」由 ``test_cli_conversation.py`` 保证。这里只测 server 这一层：
创建 → 投递 → 忙时拒绝 → 跨轮实时流 → 结束 → 空闲回收。
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from dm_agent.server.runs import RunRegistry

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


# 桩对话 agent：每读到一行 {"task": ...} 就写一段 run_start/step/run_end，
# 读到 EOF 就退出。turn_delay 用来制造「这一轮还在跑」的窗口。
STUB_CONVERSATION = """
import json, sys, time
path, turn_delay = sys.argv[1], float(sys.argv[2])
sys.stdin.reconfigure(encoding="utf-8")
seq = 0
def emit(handle, event, payload):
    global seq
    seq += 1
    handle.write(json.dumps({
        "id": "stub-%04d" % seq,
        "parent_id": "stub-%04d" % (seq - 1) if seq > 1 else "",
        "timestamp": "2026-02-01T00:00:00+00:00",
        "run_id": "stub-chat",
        "event": event,
        "payload": payload,
    }, ensure_ascii=False) + "\\n")
    handle.flush()
with open(path, "a", encoding="utf-8") as handle:
    emit(handle, "runtime", {"provider": "deepseek"})
    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if message.get("type") == "reset":
            emit(handle, "conversation_reset", {})
            continue
        task = message.get("task")
        if not task:
            continue
        emit(handle, "run_start", {"schema_version": "2.0", "task": task})
        time.sleep(turn_delay)
        emit(handle, "step", {"step_number": 1, "action": "finish", "observation": "ok"})
        emit(handle, "run_end", {
            "status": "success",
            "final_answer": "answer for " + task,
            "metadata": {"status": "success"},
        })
    emit(handle, "conversation_end", {"turns": 0, "reason": "eof"})
"""


@pytest.fixture
def fake_conversation(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """把 ``build_conversation_argv`` 换成读 stdin 的桩进程。"""

    def install(*, turn_delay: float = 0.0) -> None:
        def fake_argv(_spec: object, *, trace_path: Path) -> list[str]:
            return [sys.executable, "-u", "-c", STUB_CONVERSATION, str(trace_path), str(turn_delay)]

        monkeypatch.setattr(
            "dm_agent.server.routes.conversations.build_conversation_argv", fake_argv
        )

    return install


@pytest.fixture
def writable_client(make_client: Callable[..., TestClient], tmp_path: Path) -> TestClient:
    """可写模式的 client，workspace 指向临时目录——绝不让测试里的 agent 碰真仓库。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return make_client(workspace=workspace)


def registry_of(client: TestClient) -> RunRegistry:
    registry = client.app.state.registry  # type: ignore[attr-defined]
    assert isinstance(registry, RunRegistry)
    return registry


def open_conversation(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/conversations", json={"provider": "deepseek"})
    assert response.status_code == 201, response.text
    return dict(response.json())


def wait_for_completed_turns(
    client: TestClient, conversation_id: str, count: int
) -> dict[str, Any]:
    """轮询到已完成轮数达标。桩进程很快，1.5s 是很宽松的上限。"""
    deadline = time.time() + 15.0
    payload: dict[str, Any] = {}
    while time.time() < deadline:
        payload = dict(client.get(f"/api/conversations/{conversation_id}").json())
        if payload.get("completed_turns", 0) >= count:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"等到超时仍只跑完 {payload.get('completed_turns')} 轮：{payload}")


def test_a_new_conversation_starts_idle_with_no_turns(
    writable_client: TestClient, fake_conversation: Callable[..., None]
) -> None:
    """开对话时还没有任务，所以状态是 idle 而不是 running。"""
    fake_conversation()
    created = open_conversation(writable_client)
    assert created["kind"] == "conversation"
    assert created["status"] == "idle"
    assert created["submitted_turns"] == 0
    assert created["session"].startswith("chat-")
    writable_client.delete(f"/api/conversations/{created['run_id']}")


def test_turns_run_sequentially_and_land_in_one_session_log(
    writable_client: TestClient, fake_conversation: Callable[..., None], tmp_path: Path
) -> None:
    """两轮写进**同一份** JSONL，形成两段 run。这是多轮在存储侧的样子。"""
    fake_conversation()
    conversation = open_conversation(writable_client)
    conversation_id = conversation["run_id"]

    for task in ("第一轮任务", "第二轮任务"):
        response = writable_client.post(
            f"/api/conversations/{conversation_id}/turns", json={"task": task}
        )
        assert response.status_code == 200, response.text
        wait_for_completed_turns(writable_client, conversation_id, response.json()["turn"]["index"])

    final = wait_for_completed_turns(writable_client, conversation_id, 2)
    assert final["submitted_turns"] == 2
    assert [turn["task"] for turn in final["turns"]] == ["第一轮任务", "第二轮任务"]
    # 首轮任务成为整个对话的标题。
    assert final["task"] == "第一轮任务"

    entries = writable_client.get(
        "/api/sessions/entries", params={"name": conversation["session"]}
    ).json()["entries"]
    starts = [entry for entry in entries if entry["event"] == "run_start"]
    assert [entry["payload"]["task"] for entry in starts] == ["第一轮任务", "第二轮任务"]

    writable_client.delete(f"/api/conversations/{conversation_id}")


def test_submitting_while_busy_is_rejected(
    writable_client: TestClient, fake_conversation: Callable[..., None]
) -> None:
    """ReactAgent 是顺序执行的：上一轮没跑完就再投一轮必须被明确拒绝，不能排队。"""
    fake_conversation(turn_delay=5.0)
    conversation_id = open_conversation(writable_client)["run_id"]

    first = writable_client.post(
        f"/api/conversations/{conversation_id}/turns", json={"task": "慢的一轮"}
    )
    assert first.status_code == 200

    # 等桩进程真的进入这一轮（写出 run_start）。
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if writable_client.get(f"/api/conversations/{conversation_id}").json()["busy"]:
            break
        time.sleep(0.05)

    second = writable_client.post(
        f"/api/conversations/{conversation_id}/turns", json={"task": "抢跑的一轮"}
    )
    assert second.status_code == 409
    assert "上一轮" in second.json()["detail"]

    writable_client.delete(f"/api/conversations/{conversation_id}")


def test_stream_spans_multiple_turns(
    writable_client: TestClient, fake_conversation: Callable[..., None]
) -> None:
    """**这条是多轮实时流的核心**：一条 SSE 连接要横跨两轮，只在对话结束时才 done。

    单次运行的流每轮都得重连；对话流不用，所以前端切视图、甚至刷新页面都能接回来。
    """
    fake_conversation()
    conversation = open_conversation(writable_client)
    conversation_id = conversation["run_id"]

    for task in ("轮一", "轮二"):
        writable_client.post(f"/api/conversations/{conversation_id}/turns", json={"task": task})
        wait_for_completed_turns(writable_client, conversation_id, 1 if task == "轮一" else 2)
    writable_client.delete(f"/api/conversations/{conversation_id}")

    with writable_client.stream("GET", f"/api/conversations/{conversation_id}/stream") as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    tasks = [
        json.loads(line[len("data: ") :]) for line in body.splitlines() if line.startswith("data: ")
    ]
    starts = [entry for entry in tasks if entry.get("event") == "run_start"]
    assert [entry["payload"]["task"] for entry in starts] == ["轮一", "轮二"]
    assert body.count("event: done") == 1


def test_ending_a_conversation_stops_the_process(
    writable_client: TestClient, fake_conversation: Callable[..., None]
) -> None:
    """结束 = 关 stdin 让 agent 自己收尾。会话日志保留，仍然可审计。"""
    fake_conversation()
    conversation = open_conversation(writable_client)
    conversation_id = conversation["run_id"]
    writable_client.post(f"/api/conversations/{conversation_id}/turns", json={"task": "唯一一轮"})
    wait_for_completed_turns(writable_client, conversation_id, 1)

    response = writable_client.delete(f"/api/conversations/{conversation_id}")
    assert response.status_code == 200
    assert response.json()["stopped"] is True

    after = writable_client.get(f"/api/conversations/{conversation_id}").json()
    assert after["status"] in {"cancelled", "completed"}
    # 被结束的对话，日志一条不删。
    listed = writable_client.get("/api/sessions").json()["sessions"]
    assert any(card["name"] == conversation["session"] for card in listed)


def test_turns_on_a_finished_conversation_are_rejected(
    writable_client: TestClient, fake_conversation: Callable[..., None]
) -> None:
    fake_conversation()
    conversation_id = open_conversation(writable_client)["run_id"]
    writable_client.delete(f"/api/conversations/{conversation_id}")

    response = writable_client.post(
        f"/api/conversations/{conversation_id}/turns", json={"task": "太晚了"}
    )
    assert response.status_code == 409
    assert "已经结束" in response.json()["detail"]


def test_unknown_conversation_is_404(writable_client: TestClient) -> None:
    assert writable_client.get("/api/conversations/nope").status_code == 404
    assert (
        writable_client.post("/api/conversations/nope/turns", json={"task": "x"}).status_code == 404
    )


def test_reflexion_is_rejected_with_a_readable_reason(writable_client: TestClient) -> None:
    """开着 Reflexion 建对话必须拿到 400 + 一句人话，而不是一个立刻 exit 2 的子进程。"""
    response = writable_client.post(
        "/api/conversations",
        json={"provider": "deepseek", "options": {"enable_reflexion": True}},
    )
    assert response.status_code == 400
    assert "Reflexion" in response.json()["detail"]


def test_a_run_id_is_not_a_conversation_id(
    writable_client: TestClient, fake_conversation: Callable[..., None]
) -> None:
    """两个注册表是同一个，所以必须按 kind 区分——否则能拿对话端点去操作一次性运行。"""
    fake_conversation()
    conversation_id = open_conversation(writable_client)["run_id"]
    assert writable_client.get(f"/api/runs/{conversation_id}").status_code == 200
    writable_client.delete(f"/api/conversations/{conversation_id}")


def test_idle_conversations_are_reaped(
    writable_client: TestClient, fake_conversation: Callable[..., None]
) -> None:
    """长驻进程必须有回收器，否则「开了对话就关浏览器」会一直漏一个 agent 进程。"""
    fake_conversation()
    conversation_id = open_conversation(writable_client)["run_id"]
    registry = registry_of(writable_client)

    # 空闲判定用的是 last_activity，直接把它推到过去即可，不用真等 30 分钟。
    record = registry.get(conversation_id)
    assert record is not None
    record.last_activity = time.time() - 10_000

    assert registry.reap_idle() == (conversation_id,)
    assert registry.get(conversation_id).is_running is False  # type: ignore[union-attr]


def test_busy_conversations_are_never_reaped(
    writable_client: TestClient, fake_conversation: Callable[..., None]
) -> None:
    """正在跑一轮的对话，哪怕投递时间很久以前，也不能被当成空闲收掉。"""
    fake_conversation(turn_delay=5.0)
    conversation_id = open_conversation(writable_client)["run_id"]
    writable_client.post(f"/api/conversations/{conversation_id}/turns", json={"task": "慢活"})

    registry = registry_of(writable_client)
    deadline = time.time() + 10.0
    while time.time() < deadline:
        record = registry.get(conversation_id)
        assert record is not None
        if record.is_busy:
            break
        time.sleep(0.05)

    record = registry.get(conversation_id)
    assert record is not None and record.is_busy
    record.last_activity = time.time() - 10_000
    assert registry.reap_idle() == ()

    writable_client.delete(f"/api/conversations/{conversation_id}")


def test_read_only_mode_blocks_every_conversation_endpoint(
    make_client: Callable[..., TestClient],
) -> None:
    """只读展厅不能发起对话——它和「发起运行」一样是会真实改工作区的写操作。"""
    client = make_client(read_only=True)
    assert client.post("/api/conversations", json={"provider": "deepseek"}).status_code == 403
    assert client.get("/api/conversations").status_code == 403
    assert client.post("/api/conversations/x/turns", json={"task": "y"}).status_code == 403
    assert client.delete("/api/conversations/x").status_code == 403


def test_capacity_is_shared_with_one_off_runs(
    writable_client: TestClient, fake_conversation: Callable[..., None], tmp_path: Path
) -> None:
    """对话和一次性运行抢的是同一个工作区，并发上限必须共用一份。"""
    fake_conversation()
    registry = registry_of(writable_client)
    opened = [open_conversation(writable_client)["run_id"] for _ in range(2)]
    assert registry.at_capacity() is True

    blocked = writable_client.post("/api/conversations", json={"provider": "deepseek"})
    assert blocked.status_code == 409

    for conversation_id in opened:
        writable_client.delete(f"/api/conversations/{conversation_id}")
