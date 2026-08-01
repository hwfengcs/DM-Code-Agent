"""只读端点的契约测试。

这些断言的价值在于：**Web 控制台和 `dm-agent-trace` 必须给出同一套结论**。
所以测试不只检查 HTTP 200，而是直接钉住 `analyze_events` 的具体判定
（失败阶段、恢复、验证缺口、健康度评级），一旦哪天 server 层自己算了一遍
而不是复用 tracing，这里就会红。

全部用例**不需要任何 API key**。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from dm_agent.tracing.analysis import analyze_events
from dm_agent.tracing.session import load_session_entries

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_health_and_meta_shape(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"

    meta = client.get("/api/meta").json()
    assert meta["server"]["read_only"] is False
    assert meta["server"]["auth_required"] is True
    assert {provider["name"] for provider in meta["providers"]} == {
        "deepseek",
        "openai",
        "claude",
        "gemini",
    }
    # 17 个内置工具，与 README 声明一致。
    assert len(meta["tools"]) == 17
    # 开关目录必须同时覆盖两类，前端才能渲染出「护栏默认开 / 行为默认关」的分组。
    categories = {item["category"] for item in meta["capabilities"]}
    assert {"guardrail", "behavior"} <= categories


def test_meta_never_leaks_api_keys(client: TestClient, monkeypatch) -> None:
    """只回报 key 配没配，绝不回报值。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-super-secret-value")
    body = client.get("/api/meta").text
    assert "sk-super-secret-value" not in body

    providers = {item["name"]: item for item in json.loads(body)["providers"]}
    assert providers["deepseek"]["api_key_present"] is True


def test_list_sessions_ranks_and_grades(client: TestClient) -> None:
    payload = client.get("/api/sessions").json()
    by_name = {card["name"]: card for card in payload["sessions"]}
    assert set(by_name) == {"recovered.jsonl", "clean.jsonl"}
    assert payload["aggregate"]["total"] == 2
    assert payload["aggregate"]["by_status"] == {"success": 2}
    # 两次运行都成功，但只有一次是「健康」的——这正是本项目要讲的那句话。
    assert payload["aggregate"]["by_health"] == {"good": 1, "warning": 1}

    recovered = by_name["recovered.jsonl"]
    assert recovered["task"].startswith("If reading missing.txt fails")
    assert recovered["step_count"] == 3
    assert recovered["replan_count"] == 1
    assert recovered["run_count"] == 1
    assert recovered["health"]["grade"] == "warning"
    assert "verification_gap" in recovered["health"]["issues"]

    assert by_name["clean.jsonl"]["health"]["grade"] == "good"
    assert by_name["clean.jsonl"]["health"]["issues"] == []


def test_list_sessions_never_leaks_absolute_paths(client: TestClient, sessions_dir: Path) -> None:
    body = client.get("/api/sessions").text
    assert str(sessions_dir) not in body
    assert sessions_dir.as_posix() not in body


def test_summary_matches_cli_semantics(client: TestClient) -> None:
    summary = client.get("/api/sessions/summary", params={"name": "recovered.jsonl"}).json()[
        "summary"
    ]
    assert summary["status"] == "success"
    assert summary["provider"] == "deepseek"
    assert summary["final_answer"] == "任务完成：recovered"
    assert [step["action"] for step in summary["steps"]] == [
        "read_file",
        "create_file",
        "task_complete",
    ]
    assert [step["action"] for step in summary["plan_steps"]] == ["read_file", "create_file"]


def test_analysis_reports_recovery_and_verification_gap(client: TestClient) -> None:
    analysis = client.get("/api/sessions/analysis", params={"name": "recovered.jsonl"}).json()[
        "analysis"
    ]
    assert analysis["primary_failure_stage"] == "tool"
    assert analysis["final_failure_stage"] == "none"
    assert analysis["recovery"] == {
        "failure_event_count": 1,
        "first_failure_step": 1,
        "first_failure_event": "tool_call",
        "replan_count": 1,
        "replanned_after_failure": True,
        "recovered": True,
    }
    assert analysis["verification"]["gap"] is True
    assert analysis["verification"]["count"] == 0
    assert "verification_gap" in analysis["signals"]
    assert "replanned_after_failure" in analysis["signals"]


def test_analysis_is_byte_for_byte_the_tracing_layer(
    client: TestClient, sessions_dir: Path
) -> None:
    """server 不许自己算诊断——必须与直接调 tracing 纯函数的结果完全一致。"""
    for name in ("recovered.jsonl", "clean.jsonl"):
        via_api = client.get("/api/sessions/analysis", params={"name": name}).json()["analysis"]
        via_lib = analyze_events(load_session_entries(sessions_dir / name))
        assert via_api == json.loads(json.dumps(via_lib, ensure_ascii=False))


def test_clean_run_has_verification_before_finish(client: TestClient) -> None:
    analysis = client.get("/api/sessions/analysis", params={"name": "clean.jsonl"}).json()[
        "analysis"
    ]
    assert analysis["verification"]["before_finish"] is True
    assert analysis["verification"]["gap"] is False
    assert analysis["trace_health"] == {"score": 1.0, "grade": "good", "issues": []}


def test_entries_are_paginated_and_keep_the_id_chain(client: TestClient) -> None:
    first = client.get(
        "/api/sessions/entries", params={"name": "recovered.jsonl", "limit": 3}
    ).json()
    assert first["total"] == 13
    assert first["offset"] == 0
    assert len(first["entries"]) == 3
    assert [entry["event"] for entry in first["entries"]] == ["runtime", "run_start", "plan"]
    # parent_id 链必须原样保留——前端画会话树靠的就是它。
    assert first["entries"][0]["parent_id"] == ""
    assert first["entries"][1]["parent_id"] == first["entries"][0]["id"]

    tail = client.get(
        "/api/sessions/entries", params={"name": "recovered.jsonl", "offset": 12, "limit": 10}
    ).json()
    assert len(tail["entries"]) == 1
    assert tail["entries"][0]["event"] == "run_end"


def test_diff_reports_behavioral_change(client: TestClient) -> None:
    payload = client.get(
        "/api/sessions/diff", params={"a": "recovered.jsonl", "b": "clean.jsonl"}
    ).json()
    assert payload["a"] == "recovered.jsonl"
    assert payload["b"] == "clean.jsonl"
    # 具体字段由 tracing.diff_events 定义，这里只钉住「两次运行行为不同」这个结论。
    assert payload["diff"]
    assert payload["diff"] != {}


def test_fork_creates_a_new_session_inside_sessions_dir(
    client: TestClient, sessions_dir: Path
) -> None:
    response = client.post(
        "/api/sessions/fork",
        json={"name": "recovered.jsonl", "at": "recovrd1-0007"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["forked_from_entry_id"] == "recovrd1-0007"
    assert body["entry_count"] == 7
    # 响应里只有相对名，没有绝对路径。
    assert body["source"] == "recovered.jsonl"
    assert not Path(body["output"]).is_absolute()

    forked = sessions_dir / body["output"]
    assert forked.is_file()
    entries = load_session_entries(forked)
    # 源会话前 7 条 + 一条 fork 记录，且 fork 条目指回分叉点。
    assert len(entries) == 8
    assert entries[-1]["event"] == "fork"
    assert entries[-1]["parent_id"] == "recovrd1-0007"
    # 分叉出来的会话立刻能被列出来。
    assert body["output"] in {
        card["name"] for card in client.get("/api/sessions").json()["sessions"]
    }


def test_fork_rejects_unknown_entry(client: TestClient) -> None:
    response = client.post(
        "/api/sessions/fork", json={"name": "recovered.jsonl", "at": "no-such-entry"}
    )
    assert response.status_code == 400


def test_unreadable_session_does_not_break_the_listing(
    client: TestClient, sessions_dir: Path
) -> None:
    (sessions_dir / "broken.jsonl").write_text("{not json\n", encoding="utf-8")
    payload = client.get("/api/sessions").json()
    assert payload["aggregate"]["unreadable"] == 1
    assert [error["name"] for error in payload["errors"]] == ["broken.jsonl"]
    # 好文件照常返回。
    assert len(payload["sessions"]) == 2


def test_listing_reflects_appended_entries(client: TestClient, sessions_dir: Path) -> None:
    """会话卡片有 mtime+size 缓存，追加写之后必须失效重算。"""
    before = _card(client, "clean.jsonl")
    with (sessions_dir / "clean.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "id": "cleanru1-0011",
                    "parent_id": "cleanru1-0010",
                    "timestamp": "2026-02-01T00:00:20+00:00",
                    "run_id": "run-clean",
                    "event": "step",
                    "payload": {"step_number": 4, "action": "read_file", "observation": "ok"},
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    after = _card(client, "clean.jsonl")
    assert after["event_count"] == before["event_count"] + 1
    assert after["step_count"] == before["step_count"] + 1


def _card(client: TestClient, name: str) -> dict:
    cards = client.get("/api/sessions").json()["sessions"]
    return next(card for card in cards if card["name"] == name)


def test_missing_session_is_404(client: TestClient) -> None:
    assert client.get("/api/sessions/summary", params={"name": "nope.jsonl"}).status_code == 404


def test_root_without_frontend_build_is_self_explanatory(
    make_client: Callable[..., TestClient], tmp_path: Path
) -> None:
    """前端还没构建时给一条能照着敲的提示，而不是 404。

    显式指向一个空目录，而不是让它去捡随包分发的 ``dm_agent/server/static``——
    否则这条断言的结果会取决于本地有没有跑过 ``npm run build``。
    """
    empty = tmp_path / "no-frontend"
    empty.mkdir()
    body = make_client(static_dir=empty).get("/").json()
    assert "npm run build" in body["build"]


def test_built_frontend_is_served_with_spa_fallback(
    make_client: Callable[..., TestClient], tmp_path: Path
) -> None:
    """前端产物存在时：根路径给 index.html，路径式深链回落到 index.html，API 不被吃掉。

    这条测试钉住一个真实踩过的坑：``StaticFiles.get_response`` 找不到文件时是
    **raise HTTPException(404)**，不是返回 404 响应。所以回落逻辑必须 except，
    判 ``response.status_code == 404`` 永远不会生效。
    """
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (static / "assets").mkdir()
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")

    client = make_client(static_dir=static)

    root = client.get("/")
    assert root.status_code == 200
    assert "id=root" in root.text

    # 真实存在的资源照常返回自己。
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text

    # 路径式深链回落到 index.html，而不是 JSON 404。
    deep = client.get("/run/clean.jsonl")
    assert deep.status_code == 200
    assert "id=root" in deep.text

    # 静态挂载在 / 兜底，但绝不能吃掉 /api/*。
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/sessions").json()["aggregate"]["total"] == 2


def test_woff2_is_served_with_the_right_mime(
    make_client: Callable[..., TestClient], tmp_path: Path
) -> None:
    """前端自带的 Geist 字体必须以 ``font/woff2`` 发出。

    Python 的 ``mimetypes`` 表里没有 woff2，不显式注册就会回落到
    ``application/octet-stream``。浏览器加载 @font-face 时不强制校验 MIME，所以
    这个问题在本地看不出来——直到有人在前面架了开严格 nosniff 策略的反向代理。
    """
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    # woff2 的魔数，内容不重要，这里只关心响应头。
    (static / "assets" / "Geist.woff2").write_bytes(b"wOF2\x00\x00\x00\x00")

    response = make_client(static_dir=static).get("/assets/Geist.woff2")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("font/woff2")


def test_make_client_accepts_read_only(make_client: Callable[..., TestClient]) -> None:
    read_only = make_client(read_only=True)
    assert read_only.get("/api/meta").json()["server"]["read_only"] is True
    # 只读模式下审计能力完全不受影响。
    assert read_only.get("/api/sessions").json()["aggregate"]["total"] == 2
    assert (
        read_only.get("/api/sessions/analysis", params={"name": "clean.jsonl"}).status_code == 200
    )
