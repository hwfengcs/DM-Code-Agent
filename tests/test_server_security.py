"""安全模型的测试：token 校验、只读模式、路径边界。

这三条是「敢不敢把这个后端拿出去传播」的前提，所以每条都要有失败用例，
不能只测 happy path。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from dm_agent.server.settings import (
    ServerSettings,
    SessionPathError,
    generate_token,
    is_loopback_host,
    resolve_session_path,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


# --- token ---------------------------------------------------------------


def test_api_requires_token(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    del client.headers["Authorization"]
    for path in ("/api/health", "/api/meta", "/api/sessions"):
        assert client.get(path).status_code == 401, path


def test_wrong_token_is_rejected(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    client.headers["Authorization"] = "Bearer not-the-token"
    assert client.get("/api/sessions").status_code == 401


def test_query_token_works_for_eventsource(make_client: Callable[..., TestClient]) -> None:
    """浏览器 EventSource 无法设置请求头，SSE 只能走查询参数——这条路必须通。"""
    client = make_client(token="tok-abc")
    del client.headers["Authorization"]
    assert client.get("/api/sessions", params={"token": "tok-abc"}).status_code == 200
    assert client.get("/api/sessions", params={"token": "tok-xyz"}).status_code == 401


def test_no_token_mode_allows_anonymous(make_client: Callable[..., TestClient]) -> None:
    client = make_client(token="")
    # token 为空时 fixture 本来就没设这个头，pop 掉是为了断言「确实不需要它」。
    client.headers.pop("Authorization", None)
    assert client.get("/api/sessions").status_code == 200


def test_generated_tokens_are_unique_and_long() -> None:
    tokens = {generate_token() for _ in range(32)}
    assert len(tokens) == 32
    assert all(len(token) >= 32 for token in tokens)


# --- 绑定地址 fail closed ------------------------------------------------


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("::1", True),
        ("[::1]", True),
        ("0.0.0.0", False),
        ("192.168.1.10", False),
        ("example.com", False),
        ("not-an-address", False),
    ],
)
def test_loopback_detection(host: str, expected: bool) -> None:
    assert is_loopback_host(host) is expected


def test_non_loopback_bind_requires_token(tmp_path: Path) -> None:
    """没有 token 就绑到 0.0.0.0 必须直接构造失败，而不是起起来再说。"""
    with pytest.raises(ValueError, match="token"):
        ServerSettings(sessions_dir=tmp_path, host="0.0.0.0")

    # 给了 token 就允许。
    settings = ServerSettings(sessions_dir=tmp_path, host="0.0.0.0", token="t")
    assert settings.auth_required is True


def test_public_url_carries_token(tmp_path: Path) -> None:
    settings = ServerSettings(sessions_dir=tmp_path, port=9000, token="abc")
    assert settings.public_url() == "http://127.0.0.1:9000/?token=abc"
    # 通配绑定要打印一个真的能点开的地址，不能打印 0.0.0.0。
    wildcard = ServerSettings(sessions_dir=tmp_path, host="0.0.0.0", port=9000, token="abc")
    assert wildcard.public_url().startswith("http://127.0.0.1:9000/")


# --- 只读模式 -----------------------------------------------------------


def test_read_only_blocks_fork(make_client: Callable[..., TestClient]) -> None:
    client = make_client(read_only=True)
    response = client.post(
        "/api/sessions/fork", json={"name": "recovered.jsonl", "at": "recovrd1-0007"}
    )
    assert response.status_code == 403
    assert "read-only" in response.json()["detail"]


def test_read_only_still_serves_every_audit_endpoint(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client(read_only=True)
    assert client.get("/api/sessions").status_code == 200
    assert client.get("/api/sessions/summary", params={"name": "clean.jsonl"}).status_code == 200
    assert client.get("/api/sessions/analysis", params={"name": "clean.jsonl"}).status_code == 200
    assert client.get("/api/sessions/entries", params={"name": "clean.jsonl"}).status_code == 200
    assert (
        client.get(
            "/api/sessions/diff", params={"a": "clean.jsonl", "b": "recovered.jsonl"}
        ).status_code
        == 200
    )


def test_read_only_mode_writes_nothing(
    make_client: Callable[..., TestClient], sessions_dir: Path
) -> None:
    before = sorted(path.name for path in sessions_dir.iterdir())
    client = make_client(read_only=True)
    client.get("/api/sessions")
    client.post("/api/sessions/fork", json={"name": "recovered.jsonl", "at": "recovrd1-0007"})
    assert sorted(path.name for path in sessions_dir.iterdir()) == before


# --- 路径边界 -----------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "../secrets.jsonl",
        "../../etc/passwd.jsonl",
        "sub/../../outside.jsonl",
        "/absolute.jsonl",
        "\\absolute.jsonl",
        "notes.txt",
        "recovered.jsonl.bak",
        "",
        "   ",
    ],
)
def test_resolve_session_path_rejects_bad_names(sessions_dir: Path, name: str) -> None:
    settings = ServerSettings(sessions_dir=sessions_dir)
    with pytest.raises(SessionPathError):
        resolve_session_path(settings, name)


def test_resolve_session_path_accepts_subdirectories(sessions_dir: Path) -> None:
    nested = sessions_dir / "nested" / "run.jsonl"
    nested.parent.mkdir(parents=True)
    nested.write_text("{}\n", encoding="utf-8")
    settings = ServerSettings(sessions_dir=sessions_dir)
    assert resolve_session_path(settings, "nested/run.jsonl") == nested.resolve()


@pytest.mark.parametrize(
    "name",
    ["../escaped.jsonl", "/tmp/escaped.jsonl", "escaped.txt", "sub/../../escaped.jsonl"],
)
def test_fork_output_cannot_escape_sessions_dir(
    make_client: Callable[..., TestClient], sessions_dir: Path, name: str
) -> None:
    client = make_client()
    response = client.post(
        "/api/sessions/fork",
        json={"name": "recovered.jsonl", "at": "recovrd1-0007", "output": name},
    )
    assert response.status_code == 400
    # 确认真的没在目录外落下文件。
    assert not (sessions_dir.parent / "escaped.jsonl").exists()


def test_traversal_via_api_is_404(make_client: Callable[..., TestClient], tmp_path: Path) -> None:
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    client = make_client()
    response = client.get("/api/sessions/summary", params={"name": "../outside.jsonl"})
    assert response.status_code == 404
