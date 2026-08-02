"""运行端点的端到端测试。

这里 spawn 的是**真的** ``python -m dm_agent.cli`` 子进程，但刻意不配 API key——
没有 key 的 CLI 会很快自己退出，这足以覆盖完整的生命周期（创建 → 结束 → 状态转移 →
SSE 收尾），且不花一分钱、不依赖网络。

需要「进程一直活着」的用例（取消、并发上限）直接往注册表里塞一个 sleep 子进程，
不绕道 HTTP。
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from dm_agent.server.process import RunProcess
from dm_agent.server.runs import RunRecord, RunRegistry

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


# 桩 agent：把若干条会话条目逐行写入并 flush，然后按指定退出码退出。
# 用它替换真 CLI 的原因见 fake_agent fixture 的说明。
STUB_AGENT = """
import json, sys, time
path, count, exit_code, delay = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
agent_status = sys.argv[5]
with open(path, "a", encoding="utf-8") as handle:
    for index in range(count):
        last = index == count - 1
        entry = {
            "id": "stub-%04d" % index,
            "parent_id": "stub-%04d" % (index - 1) if index else "",
            "timestamp": "2026-02-01T00:00:00+00:00",
            "run_id": "stub-run",
            "event": "run_start" if index == 0 else ("run_end" if last else "step"),
            "payload": (
                {"status": agent_status, "metadata": {"status": agent_status}}
                if last and count > 1
                else {"step_number": index}
            ),
        }
        handle.write(json.dumps(entry, ensure_ascii=False) + "\\n")
        handle.flush()
        time.sleep(delay)
sys.exit(exit_code)
"""


@pytest.fixture
def fake_agent(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """把路由里的 ``build_argv`` 换成一个写 JSONL 的桩进程。

    **为什么不 spawn 真的 CLI**：一开始这些用例靠「没配 API key 所以 CLI 会快速失败」
    来跑完生命周期。那是错的，而且真的花钱了——``load_dotenv()`` 的 ``find_dotenv()``
    是从 **调用方模块所在目录**（``dm_agent/cli/``）向上找的，子进程无论 cwd 在哪都会
    捡到仓库根的 ``.env``；而 Windows 上 ``os.environ[k] = ""`` 等于删除变量，
    子进程拿到的是「未设置」，dotenv 于是把真 key 填了回来。

    换成桩进程后这些用例**彻底离线**：不读 key、不联网、不受本地 .env 影响，
    还能精确控制退出码、agent 状态与写入节奏，从而真正测到边写边读的 SSE。
    真 argv 与真解析器的一致性由 ``tests/test_server_process.py`` 单独保证。
    """

    def install(
        *,
        entries: int = 4,
        exit_code: int = 0,
        delay: float = 0.0,
        agent_status: str = "success",
    ) -> None:
        def fake_build_argv(_spec: object, *, trace_path: Path) -> list[str]:
            return [
                sys.executable,
                "-c",
                STUB_AGENT,
                str(trace_path),
                str(entries),
                str(exit_code),
                str(delay),
                agent_status,
            ]

        monkeypatch.setattr("dm_agent.server.routes.runs.build_argv", fake_build_argv)

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


def add_sleeper(client: TestClient, tmp_path: Path, *, run_id: str = "sleeper1") -> RunRecord:
    """往注册表里塞一个长命子进程，用来测取消与并发上限。"""
    registry = registry_of(client)
    trace_path = tmp_path / f"{run_id}.jsonl"
    process = RunProcess(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path,
        trace_path=trace_path,
    )
    process.start()
    record = RunRecord(
        run_id=run_id,
        task="占位任务",
        session_name=trace_path.name,
        trace_path=trace_path,
        process=process,
    )
    registry.register(record)
    return record


def wait_until_finished(client: TestClient, run_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    payload: dict = {}
    while time.time() < deadline:
        payload = client.get(f"/api/runs/{run_id}").json()
        if payload["status"] != "running":
            return payload
        time.sleep(0.2)
    pytest.fail(f"运行 {run_id} 在 {timeout}s 内没有结束：{payload}")


# --- 请求校验 -----------------------------------------------------------


def test_rejects_empty_task(writable_client: TestClient) -> None:
    response = writable_client.post("/api/runs", json={"task": "   ", "provider": "deepseek"})
    assert response.status_code == 400


def test_rejects_unknown_provider(writable_client: TestClient) -> None:
    response = writable_client.post("/api/runs", json={"task": "x", "provider": "evil"})
    assert response.status_code == 400
    assert "provider" in response.json()["detail"]


def test_rejects_out_of_range_option(writable_client: TestClient) -> None:
    response = writable_client.post(
        "/api/runs",
        json={"task": "x", "provider": "deepseek", "options": {"max_steps": 99999}},
    )
    assert response.status_code == 400


def test_missing_task_is_a_validation_error(writable_client: TestClient) -> None:
    """pydantic 层的校验：task 是必填且非空。"""
    assert writable_client.post("/api/runs", json={"provider": "deepseek"}).status_code == 422


# --- 只读模式 -----------------------------------------------------------


def test_read_only_blocks_every_run_endpoint(
    make_client: Callable[..., TestClient], tmp_path: Path
) -> None:
    client = make_client(read_only=True, workspace=tmp_path)
    assert client.post("/api/runs", json={"task": "x", "provider": "deepseek"}).status_code == 403
    assert client.get("/api/runs").status_code == 403
    assert client.delete("/api/runs/whatever").status_code == 403
    assert client.get("/api/runs/whatever/stream").status_code == 403


def test_run_endpoints_require_token(
    make_client: Callable[..., TestClient], tmp_path: Path
) -> None:
    client = make_client(workspace=tmp_path)
    del client.headers["Authorization"]
    assert client.post("/api/runs", json={"task": "x", "provider": "deepseek"}).status_code == 401
    assert client.get("/api/runs").status_code == 401


# --- 生命周期 -----------------------------------------------------------


def test_successful_run_lifecycle(
    writable_client: TestClient, fake_agent: Callable[..., None]
) -> None:
    """完整生命周期：创建 → 子进程写完条目退出 → 状态收敛为 completed。"""
    fake_agent(entries=4, exit_code=0)

    created = writable_client.post(
        "/api/runs",
        json={"task": "写一个 hello 文件", "provider": "deepseek", "options": {"max_steps": 2}},
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "running"
    assert payload["pid"] > 0
    assert payload["session"].endswith(".jsonl")
    run_id = payload["run_id"]

    # 立刻能查到，并且出现在列表里。
    assert writable_client.get(f"/api/runs/{run_id}").json()["run_id"] == run_id
    assert run_id in [item["run_id"] for item in writable_client.get("/api/runs").json()["runs"]]

    final = wait_until_finished(writable_client, run_id)
    assert final["status"] == "completed"
    assert final["agent_status"] == "success"
    assert final["exit_code"] == 0
    assert final["finished_at"] is not None

    # 运行产生的会话立刻能通过只读端点审计——运行与审计共用同一份 JSONL。
    listed = writable_client.get("/api/sessions").json()["sessions"]
    assert payload["session"] in [card["name"] for card in listed]


def test_zero_exit_with_unfinished_agent_is_not_reported_as_completed(
    writable_client: TestClient, fake_agent: Callable[..., None]
) -> None:
    """退出码 0 不等于 agent 做完了。

    这条钉住一个端到端实测抓到的真 bug：``dm-agent`` 对 ``max_steps_exceeded``
    也返回 0（那不算 CLI 失败，只是 agent 没做完），而控制台当时只看退出码，
    于是把一次「步数耗尽」报成了 completed。真相在会话日志的 ``run_end.status`` 里。
    """
    fake_agent(entries=4, exit_code=0, agent_status="max_steps_exceeded")

    run_id = writable_client.post("/api/runs", json={"task": "x", "provider": "deepseek"}).json()[
        "run_id"
    ]
    final = wait_until_finished(writable_client, run_id)
    assert final["exit_code"] == 0
    assert final["agent_status"] == "max_steps_exceeded"
    assert final["status"] == "incomplete"


def test_missing_run_end_falls_back_to_exit_code(
    writable_client: TestClient, fake_agent: Callable[..., None]
) -> None:
    """拿不到 agent 状态时退回旧口径，不能因此把成功的运行判成失败。"""
    fake_agent(entries=1, exit_code=0)  # 只有一条 run_start，没有 run_end

    run_id = writable_client.post("/api/runs", json={"task": "x", "provider": "deepseek"}).json()[
        "run_id"
    ]
    final = wait_until_finished(writable_client, run_id)
    assert final["agent_status"] == ""
    assert final["status"] == "completed"


def test_failed_run_surfaces_the_exit_code_and_output(
    writable_client: TestClient, fake_agent: Callable[..., None]
) -> None:
    """子进程非零退出时状态要收敛为 failed，且失败原因可见。"""
    fake_agent(entries=1, exit_code=2)

    run_id = writable_client.post("/api/runs", json={"task": "x", "provider": "deepseek"}).json()[
        "run_id"
    ]
    final = wait_until_finished(writable_client, run_id)
    assert final["status"] == "failed"
    assert final["exit_code"] == 2


def test_stream_terminates_when_no_log_was_ever_written(
    writable_client: TestClient, fake_agent: Callable[..., None]
) -> None:
    """子进程没能建出会话日志时，SSE 也必须收尾，不能把连接永远挂住。"""
    fake_agent(entries=0, exit_code=1)

    run_id = writable_client.post("/api/runs", json={"task": "x", "provider": "deepseek"}).json()[
        "run_id"
    ]
    wait_until_finished(writable_client, run_id)

    with writable_client.stream("GET", f"/api/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        # 反代缓冲会把「实时」变成「一次性」，这个头必须在。
        assert response.headers["x-accel-buffering"] == "no"
        body = "".join(response.iter_text())

    assert "event: status" in body
    assert "event: done" in body


def test_stream_delivers_entries_of_a_live_run(
    writable_client: TestClient, fake_agent: Callable[..., None]
) -> None:
    """真正的实时场景：一边有子进程在追加写，一边把新条目推给客户端。

    桩进程每写一条 sleep 一下，确保 SSE 连上时它还在跑——覆盖的是边写边读，
    而不是「等它写完再一次性读」。
    """
    fake_agent(entries=5, exit_code=0, delay=0.15)

    run_id = writable_client.post("/api/runs", json={"task": "x", "provider": "deepseek"}).json()[
        "run_id"
    ]
    with writable_client.stream("GET", f"/api/runs/{run_id}/stream") as response:
        body = "".join(response.iter_text())

    # 5 条条目一条不少，行号连续，最后以 done 收尾。
    assert body.count("event: entry") == 5
    for index in range(5):
        assert f"id: {index}\n" in body
    assert '"event": "run_start"' in body
    assert '"event": "run_end"' in body
    assert body.index("event: done") > body.rindex("event: entry")


def test_stream_replays_an_existing_session(
    writable_client: TestClient, tmp_path: Path, sessions_dir: Path
) -> None:
    """把一个已完成的会话挂到运行记录上，确认 SSE 把条目按行号发全。"""
    registry = registry_of(writable_client)
    source = sessions_dir / "clean.jsonl"
    process = RunProcess([sys.executable, "-c", "pass"], cwd=tmp_path, trace_path=source)
    process.start()
    deadline = time.time() + 10
    while time.time() < deadline and process.poll() is None:
        time.sleep(0.05)

    registry.register(
        RunRecord(
            run_id="replay01",
            task="重播",
            session_name="clean.jsonl",
            trace_path=source,
            process=process,
        )
    )

    with writable_client.stream("GET", "/api/runs/replay01/stream") as response:
        body = "".join(response.iter_text())

    # 会话里有 10 条条目，每条一个 entry 事件，id 从 0 递增。
    assert body.count("event: entry") == 10
    assert "id: 0\n" in body
    assert "id: 9\n" in body
    assert '"event": "run_end"' in body
    assert body.rstrip().endswith("}")
    assert "event: done" in body


def test_unknown_run_is_404(writable_client: TestClient) -> None:
    assert writable_client.get("/api/runs/nope").status_code == 404
    assert writable_client.delete("/api/runs/nope").status_code == 404
    assert writable_client.get("/api/runs/nope/stream").status_code == 404


# --- 取消与并发 ---------------------------------------------------------


def test_cancel_stops_the_process_and_keeps_the_log(
    writable_client: TestClient, tmp_path: Path
) -> None:
    """取消要真的杀掉进程，但**保留**已写入的会话日志——它同样是可审计的证据。"""
    record = add_sleeper(writable_client, tmp_path)
    record.trace_path.write_text('{"partial": true}\n', encoding="utf-8")

    response = writable_client.delete(f"/api/runs/{record.run_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["stopped"] is True
    assert payload["cancelled"] is True
    assert payload["status"] == "cancelled"

    deadline = time.time() + 15
    while time.time() < deadline and record.process.poll() is None:
        time.sleep(0.1)
    assert record.process.poll() is not None, "取消后子进程仍在运行"
    assert record.trace_path.exists(), "取消不应删除会话日志"


def test_cancelling_twice_reports_not_stopped(writable_client: TestClient, tmp_path: Path) -> None:
    record = add_sleeper(writable_client, tmp_path)
    assert writable_client.delete(f"/api/runs/{record.run_id}").json()["stopped"] is True
    second = writable_client.delete(f"/api/runs/{record.run_id}")
    assert second.status_code == 200
    assert second.json()["stopped"] is False


def test_concurrency_limit_returns_409(writable_client: TestClient, tmp_path: Path) -> None:
    """并发跑多个 agent 会互相踩同一个工作区，所以要挡住。"""
    first = add_sleeper(writable_client, tmp_path, run_id="sleeper1")
    second = add_sleeper(writable_client, tmp_path, run_id="sleeper2")
    try:
        response = writable_client.post("/api/runs", json={"task": "x", "provider": "deepseek"})
        assert response.status_code == 409
        assert "工作区" in response.json()["detail"]
    finally:
        for record in (first, second):
            record.process.stop(grace_seconds=1.0)


def test_capacity_frees_up_after_cancel(writable_client: TestClient, tmp_path: Path) -> None:
    registry = registry_of(writable_client)
    first = add_sleeper(writable_client, tmp_path, run_id="sleeper1")
    add_sleeper(writable_client, tmp_path, run_id="sleeper2")
    assert registry.at_capacity() is True

    writable_client.delete(f"/api/runs/{first.run_id}")
    writable_client.delete("/api/runs/sleeper2")
    assert registry.at_capacity() is False


def test_stop_all_leaves_no_orphans(writable_client: TestClient, tmp_path: Path) -> None:
    """控制台关停时必须把在跑的子进程收掉，不能留孤儿继续改工作区。"""
    records = [
        add_sleeper(writable_client, tmp_path, run_id="sleeper1"),
        add_sleeper(writable_client, tmp_path, run_id="sleeper2"),
    ]
    registry_of(writable_client).stop_all()
    for record in records:
        deadline = time.time() + 15
        while time.time() < deadline and record.process.poll() is None:
            time.sleep(0.1)
        assert record.process.poll() is not None
