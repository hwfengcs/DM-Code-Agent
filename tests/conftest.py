"""Web 控制台（``dm_agent.server``）测试的共享装置。

会话 fixture 用**固定 id / 固定时间戳**手工构造，理由和 ``test_tracing_cli.py`` 一样：
断言要能钉住具体数值，不能依赖当次运行的随机 run_id。两个 fixture 分别覆盖诊断的
两种结论——「失败后恢复但没验证」与「干净通过」。

**本文件顶层不 import fastapi。** conftest 会被整个 tests/ 目录加载，顶层导入可选依赖
会在没装 ``[web]`` extra 时让全部测试收集失败。fastapi 相关的导入一律放在 fixture 内部，
配合 ``pytest.importorskip`` 退化成 skip。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

TEST_TOKEN = "test-token-do-not-reuse"


def linked_entries(
    run_id: str,
    id_prefix: str,
    events: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """把 ``(event, payload)`` 列表串成带 id / parent_id 链的条目。"""
    entries: list[dict[str, Any]] = []
    parent_id = ""
    for index, (event, payload) in enumerate(events, start=1):
        entry_id = f"{id_prefix}-{index:04d}"
        entries.append(
            {
                "id": entry_id,
                "parent_id": parent_id,
                "timestamp": f"2026-02-01T00:00:{index - 1:02d}+00:00",
                "run_id": run_id,
                "event": event,
                "payload": payload,
            }
        )
        parent_id = entry_id
    return entries


def recovered_with_gap_entries() -> list[dict[str, Any]]:
    """读文件失败 → 重规划 → 换路径完成，但**全程没跑任何验证**。

    诊断结论应为：primary_failure_stage=tool、recovered=True、verification.gap=True、
    health.grade=warning（1.0 - 0.2 的验证缺口扣分）。
    """
    task = "If reading missing.txt fails, create recovered.txt instead."
    return linked_entries(
        "run-recovered",
        "recovrd1",
        [
            ("runtime", {"provider": "deepseek", "model": "deepseek-chat", "max_steps": 100}),
            ("run_start", {"schema_version": "2.0", "task": task}),
            (
                "plan",
                {
                    "steps": [
                        {
                            "step_number": 1,
                            "action": "read_file",
                            "reason": "先看原文件",
                            "completed": False,
                        },
                        {
                            "step_number": 2,
                            "action": "create_file",
                            "reason": "写入恢复内容",
                            "completed": False,
                        },
                    ]
                },
            ),
            ("message", {"role": "user", "step_number": 0, "kind": "task", "chars": 52}),
            ("llm_call", {"step_number": 1, "message_count": 2, "prompt_chars": 900}),
            (
                "tool_call",
                {
                    "step_number": 1,
                    "action": "read_file",
                    "failed": True,
                    "observation": "文件 missing.txt 不存在。",
                },
            ),
            (
                "step",
                {
                    "step_number": 1,
                    "action": "read_file",
                    "thought": "先读原文件",
                    "observation": "文件 missing.txt 不存在。",
                },
            ),
            ("replan", {"step_number": 1, "reason": "tool_failure", "strategy": "basic"}),
            ("llm_call", {"step_number": 2, "message_count": 4, "prompt_chars": 1200}),
            (
                "tool_call",
                {
                    "step_number": 2,
                    "action": "create_file",
                    "failed": False,
                    "observation": "已将 24 个字符写入 recovered.txt。",
                },
            ),
            (
                "step",
                {
                    "step_number": 2,
                    "action": "create_file",
                    "thought": "换个路径",
                    "observation": "已将 24 个字符写入 recovered.txt。",
                },
            ),
            (
                "step",
                {
                    "step_number": 3,
                    "action": "task_complete",
                    "thought": "完成",
                    "observation": "任务完成：recovered",
                },
            ),
            (
                "run_end",
                {
                    "status": "success",
                    "duration_seconds": 1.25,
                    "final_answer": "任务完成：recovered",
                    "metadata": {
                        "status": "success",
                        "duration_seconds": 1.25,
                        "tool_error_count": 1,
                        "replan_count": 1,
                        "parse_error_count": 0,
                    },
                },
            ),
        ],
    )


def clean_run_entries() -> list[dict[str, Any]]:
    """一次跑测试后才宣布完成的干净运行：无失败、无验证缺口、health=good。"""
    return linked_entries(
        "run-clean",
        "cleanru1",
        [
            ("runtime", {"provider": "deepseek", "model": "deepseek-chat", "max_steps": 100}),
            ("run_start", {"schema_version": "2.0", "task": "Fix retry boundary and run tests."}),
            (
                "plan",
                {
                    "steps": [
                        {
                            "step_number": 1,
                            "action": "edit_file",
                            "reason": "改边界",
                            "completed": False,
                        },
                        {
                            "step_number": 2,
                            "action": "run_tests",
                            "reason": "验证",
                            "completed": False,
                        },
                    ]
                },
            ),
            ("llm_call", {"step_number": 1, "message_count": 2, "prompt_chars": 800}),
            (
                "tool_call",
                {
                    "step_number": 1,
                    "action": "edit_file",
                    "failed": False,
                    "observation": "已替换 1 处。",
                },
            ),
            (
                "step",
                {
                    "step_number": 1,
                    "action": "edit_file",
                    "thought": "改",
                    "observation": "已替换 1 处。",
                },
            ),
            (
                "tool_call",
                {
                    "step_number": 2,
                    "action": "run_tests",
                    "failed": False,
                    "observation": "3 passed",
                },
            ),
            (
                "step",
                {
                    "step_number": 2,
                    "action": "run_tests",
                    "thought": "验证",
                    "observation": "3 passed",
                },
            ),
            (
                "step",
                {
                    "step_number": 3,
                    "action": "finish",
                    "thought": "完成",
                    "observation": "已修复并验证",
                },
            ),
            (
                "run_end",
                {
                    "status": "success",
                    "duration_seconds": 2.5,
                    "final_answer": "已修复并验证",
                    "metadata": {
                        "status": "success",
                        "duration_seconds": 2.5,
                        "tool_error_count": 0,
                    },
                },
            ),
        ],
    )


def write_session(path: Path, entries: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    """预置两个会话的 sessions 目录。"""
    directory = tmp_path / "sessions"
    write_session(directory / "recovered.jsonl", recovered_with_gap_entries())
    write_session(directory / "clean.jsonl", clean_run_entries())
    return directory


@pytest.fixture
def make_client(sessions_dir: Path) -> Iterator[Callable[..., TestClient]]:
    """按需构造 TestClient；返回的 client 已带好 token 请求头。

    fastapi 的导入放在这里而不是模块顶层：没装 ``[web]`` extra 时这个 fixture
    会 skip 用到它的测试，而不影响其余 300 个测试的收集。
    """
    pytest.importorskip("fastapi", reason="Web 控制台需要 dm-code-agent[web]")
    from fastapi.testclient import TestClient as _TestClient

    from dm_agent.server.app import create_app
    from dm_agent.server.settings import ServerSettings

    clients: list[TestClient] = []

    def factory(**overrides: Any) -> TestClient:
        settings = ServerSettings(
            sessions_dir=overrides.pop("sessions_dir", sessions_dir),
            token=overrides.pop("token", TEST_TOKEN),
            **overrides,
        )
        client = _TestClient(create_app(settings))
        if settings.token:
            client.headers["Authorization"] = f"Bearer {settings.token}"
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.close()


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    """默认配置的 client（token 已就绪，非只读）。"""
    return make_client()
