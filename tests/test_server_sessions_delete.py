"""会话删除：移入回收站、边界检查、正在写入时的保护。

**为什么是回收站而不是 unlink**：项目宪法「原始数据永不删除」说的是**会话内的条目**
（append-only、折叠只追加派生记录、原文一条不删）。用户清理一整个会话**文件**是另一
回事。搬进 ``sessions/.trash/`` 是两者之间诚实的折中——列表干净了，证据还在磁盘上。
这份测试就是把这条边界钉住的地方。
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from dm_agent.server.process import RunProcess
from dm_agent.server.routes.sessions import TRASH_DIR_NAME
from dm_agent.server.runs import RunRecord, RunRegistry

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def names_in(client: TestClient) -> list[str]:
    return [card["name"] for card in client.get("/api/sessions").json()["sessions"]]


def copy_session(source: Path, target: Path) -> Path:
    """复制一份现成的会话文件。

    刻意不从 conftest 导入那两个构造器：仓库里没有一个测试模块这么干过（tests/ 不是包），
    为一条用例引入新的导入姿势不值得。这里只需要「一份合法的会话内容」，复制即可。
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_delete_moves_the_file_into_the_trash(client: TestClient, sessions_dir: Path) -> None:
    """删除后：列表里没有了，文件还在 .trash 里躺着。"""
    response = client.delete("/api/sessions", params={"name": "clean.jsonl"})
    assert response.status_code == 200
    assert response.json()["trashed_as"] == f"{TRASH_DIR_NAME}/clean.jsonl"

    assert "clean.jsonl" not in names_in(client)
    assert not (sessions_dir / "clean.jsonl").exists()
    assert (sessions_dir / TRASH_DIR_NAME / "clean.jsonl").is_file()


def test_trashed_sessions_never_show_up_in_the_listing(
    client: TestClient, sessions_dir: Path
) -> None:
    """回收站里的 .jsonl 不能被 rglob 捞回列表——否则删了个寂寞。"""
    client.delete("/api/sessions", params={"name": "clean.jsonl"})
    listing = client.get("/api/sessions").json()
    assert all(TRASH_DIR_NAME not in card["name"] for card in listing["sessions"])
    assert listing["aggregate"]["total"] == 1


def test_any_dot_directory_is_skipped(client: TestClient, sessions_dir: Path) -> None:
    """点开头的子目录一律不进列表，不只是 .trash。"""
    copy_session(sessions_dir / "clean.jsonl", sessions_dir / ".archive" / "old.jsonl")
    assert "old.jsonl" not in " ".join(names_in(client))


def test_deleting_twice_keeps_both_copies(client: TestClient, sessions_dir: Path) -> None:
    """同名会话删两次，回收站里要留住两份，不能互相覆盖。"""
    backup = copy_session(sessions_dir / "clean.jsonl", sessions_dir / ".keep" / "clean.jsonl")
    client.delete("/api/sessions", params={"name": "clean.jsonl"})
    copy_session(backup, sessions_dir / "clean.jsonl")
    second = client.delete("/api/sessions", params={"name": "clean.jsonl"})

    assert second.status_code == 200
    assert second.json()["trashed_as"] != f"{TRASH_DIR_NAME}/clean.jsonl"
    assert len(list((sessions_dir / TRASH_DIR_NAME).glob("clean*.jsonl"))) == 2


def test_delete_is_still_bounded_by_the_sessions_dir(client: TestClient) -> None:
    """删除走的是与读取同一道边界检查：越界、绝对路径、错后缀、不存在，全是 404。"""
    for name in ("../outside.jsonl", "/etc/passwd", "clean.txt", "nope.jsonl"):
        assert client.delete("/api/sessions", params={"name": name}).status_code == 404


def test_delete_is_blocked_in_read_only_mode(make_client: Callable[..., TestClient]) -> None:
    """只读展厅要能公开分享，绝不能让访客删掉证据。"""
    read_only = make_client(read_only=True)
    assert read_only.delete("/api/sessions", params={"name": "clean.jsonl"}).status_code == 403
    assert (
        read_only.post("/api/sessions/delete", json={"names": ["clean.jsonl"]}).status_code == 403
    )


def test_bulk_delete_reports_each_name_separately(client: TestClient) -> None:
    """一个坏名字不该让整批失败——逐个报结果。"""
    response = client.post(
        "/api/sessions/delete",
        json={"names": ["clean.jsonl", "nope.jsonl", "recovered.jsonl"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["deleted"]] == ["clean.jsonl", "recovered.jsonl"]
    assert [item["name"] for item in body["failed"]] == ["nope.jsonl"]
    assert names_in(client) == []


def test_bulk_delete_rejects_an_empty_or_oversized_batch(client: TestClient) -> None:
    assert client.post("/api/sessions/delete", json={"names": []}).status_code == 422
    huge = [f"s{index}.jsonl" for index in range(500)]
    assert client.post("/api/sessions/delete", json={"names": huge}).status_code == 422


def test_a_session_being_written_cannot_be_deleted(
    make_client: Callable[..., TestClient], sessions_dir: Path, tmp_path: Path
) -> None:
    """正在被 agent 追加的会话必须拒删。

    POSIX 上删掉它只会让子进程继续写一个已经不在目录里的幽灵文件，Windows 上则直接
    因为文件锁失败。两种都不是用户按下「删除」时想要的结果。
    """
    client = make_client(workspace=tmp_path)
    registry: RunRegistry = client.app.state.registry  # type: ignore[attr-defined]
    live = sessions_dir / "clean.jsonl"
    process = RunProcess(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path,
        trace_path=live,
    )
    process.start()
    registry.register(
        RunRecord(
            run_id="live1",
            task="正在跑",
            session_name="clean.jsonl",
            trace_path=live,
            process=process,
        )
    )
    try:
        response = client.delete("/api/sessions", params={"name": "clean.jsonl"})
        assert response.status_code == 409
        assert "正在被" in response.json()["detail"]
        assert live.is_file()
    finally:
        process.stop()


def test_a_finished_run_no_longer_blocks_deletion(
    make_client: Callable[..., TestClient], sessions_dir: Path, tmp_path: Path
) -> None:
    """保护只针对**还活着**的进程；跑完了就该能删。"""
    client = make_client(workspace=tmp_path)
    registry: RunRegistry = client.app.state.registry  # type: ignore[attr-defined]
    live = sessions_dir / "clean.jsonl"
    process = RunProcess([sys.executable, "-c", "pass"], cwd=tmp_path, trace_path=live)
    process.start()
    deadline = time.time() + 15.0
    while process.poll() is None and time.time() < deadline:
        time.sleep(0.05)
    registry.register(
        RunRecord(
            run_id="done1",
            task="跑完了",
            session_name="clean.jsonl",
            trace_path=live,
            process=process,
        )
    )
    assert client.delete("/api/sessions", params={"name": "clean.jsonl"}).status_code == 200


def test_deleting_refreshes_the_card_cache(client: TestClient, sessions_dir: Path) -> None:
    """会话卡片有缓存；删完再以同名重建，列表必须显示新内容而不是缓存的旧卡片。"""
    backup = copy_session(sessions_dir / "clean.jsonl", sessions_dir / ".keep" / "clean.jsonl")
    client.get("/api/sessions")  # 预热缓存
    client.delete("/api/sessions", params={"name": "clean.jsonl"})
    copy_session(backup, sessions_dir / "clean.jsonl")
    assert "clean.jsonl" in names_in(client)


@pytest.mark.parametrize("field", ["workspace", "workspace_name"])
def test_meta_exposes_both_full_path_and_display_name(client: TestClient, field: str) -> None:
    """完整路径留给 API 消费者，界面只用 workspace_name（见 meta.py 的注释）。"""
    server = client.get("/api/meta").json()["server"]
    assert server[field]
    assert "/" not in server["workspace_name"] and "\\" not in server["workspace_name"]
