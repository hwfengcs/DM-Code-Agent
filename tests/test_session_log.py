"""会话日志的条目结构、非破坏式压缩、resume 与 fork 的测试。

这些用例全部不依赖 API key：模型响应由 ``FakeRespondClient`` 按脚本给出，
因此「开/关压缩跑同一任务，原始条目序列逐位一致」这类断言是确定性的。
"""

from __future__ import annotations

import json

import pytest

from dm_agent.core.agent import ReactAgent
from dm_agent.tools.base import Tool
from dm_agent.tracing import TraceWriter, load_session_entries, message_entries, normalize_entries


class FakeRespondClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.model = "fake-model"

    def respond(self, messages, **extra):
        if not self.responses:
            raise AssertionError("FakeRespondClient ran out of responses")
        return self.responses.pop(0)


def _action(action: str, action_input) -> str:
    return json.dumps(
        {"thought": "step", "action": action, "action_input": action_input},
        ensure_ascii=False,
    )


def _tools():
    return [
        Tool("echo", "Echo text", lambda arguments: f"echo:{arguments.get('text', '')}"),
        Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
    ]


def _run_agent(trace_path, responses, *, capture_llm_io=False, **agent_kwargs):
    writer = TraceWriter(trace_path, capture_llm_io=capture_llm_io)
    agent = ReactAgent(
        FakeRespondClient(responses),
        _tools(),
        enable_planning=False,
        trace_writer=writer,
        **agent_kwargs,
    )
    result = agent.run("say hello twice", max_steps=agent_kwargs.pop("max_steps", 8))
    writer.close()
    return result


def test_session_entries_have_unique_ids_and_a_linked_parent_chain(tmp_path):
    trace_path = tmp_path / "session.jsonl"
    _run_agent(
        trace_path,
        [_action("echo", {"text": "hi"}), _action("finish", {"answer": "done"})],
        enable_compression=False,
    )

    entries = load_session_entries(trace_path)
    ids = [entry["id"] for entry in entries]
    assert len(set(ids)) == len(ids)
    assert entries[0]["parent_id"] == ""
    assert all(
        entries[index]["parent_id"] == entries[index - 1]["id"] for index in range(1, len(entries))
    )


def test_legacy_entries_without_ids_are_normalized_on_read():
    legacy = [
        {"timestamp": "t0", "run_id": "r", "event": "run_start", "payload": {}},
        {"timestamp": "t1", "run_id": "r", "event": "run_end", "payload": {}},
    ]

    entries = normalize_entries(legacy)

    assert entries[0]["id"] == "legacy-0000"
    assert entries[0]["parent_id"] == ""
    assert entries[1]["parent_id"] == "legacy-0000"


def test_every_conversation_message_becomes_a_session_entry(tmp_path):
    trace_path = tmp_path / "session.jsonl"
    _run_agent(
        trace_path,
        [_action("echo", {"text": "hi"}), _action("finish", {"answer": "done"})],
        enable_compression=False,
    )

    messages = message_entries(load_session_entries(trace_path))
    kinds = [entry["payload"]["kind"] for entry in messages]
    assert kinds == ["task", "model_response", "tool_result", "model_response", "completion"]
    assert [entry["payload"]["role"] for entry in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]


def test_model_responses_are_hashed_unless_llm_io_capture_is_enabled(tmp_path):
    redacted_path = tmp_path / "redacted.jsonl"
    full_path = tmp_path / "full.jsonl"
    responses = [_action("finish", {"answer": "done"})]

    _run_agent(redacted_path, list(responses), enable_compression=False)
    _run_agent(full_path, list(responses), capture_llm_io=True, enable_compression=False)

    redacted = [
        entry["payload"]
        for entry in message_entries(load_session_entries(redacted_path))
        if entry["payload"]["role"] == "assistant"
    ]
    full = [
        entry["payload"]
        for entry in message_entries(load_session_entries(full_path))
        if entry["payload"]["role"] == "assistant"
    ]

    assert "content" not in redacted[0]
    assert redacted[0]["content_sha256"]
    assert redacted[0]["content_chars"] > 0
    assert full[0]["content"] == responses[0]


def test_history_entry_ids_stay_aligned_with_conversation_history(tmp_path):
    trace_path = tmp_path / "session.jsonl"
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        FakeRespondClient([_action("echo", {"text": "hi"}), _action("finish", {"answer": "done"})]),
        _tools(),
        enable_planning=False,
        enable_compression=False,
        trace_writer=writer,
    )

    agent.run("keep the ids aligned", max_steps=4)
    writer.close()

    context_ids = agent._run_context.history_entry_ids
    assert len(context_ids) == len(agent.conversation_history)
    assert all(entry_id for entry_id in context_ids)
    assert context_ids == [
        entry["id"] for entry in message_entries(load_session_entries(trace_path))
    ]


def test_reset_conversation_clears_the_entry_id_mapping(tmp_path):
    agent = ReactAgent(
        FakeRespondClient([_action("finish", {"answer": "done"})]),
        _tools(),
        enable_planning=False,
        enable_compression=False,
    )

    agent.run("reset afterwards", max_steps=2)
    assert agent.conversation_history

    agent.reset_conversation()

    assert agent.conversation_history == []
    assert agent._run_context.history_entry_ids == []


def test_find_entry_reports_unknown_and_ambiguous_references():
    from dm_agent.tracing import find_entry

    entries = normalize_entries(
        [
            {"id": "abcd-0001", "event": "run_start", "payload": {}},
            {"id": "abcd-0002", "event": "run_end", "payload": {}},
        ]
    )

    assert find_entry(entries, "abcd-0002")["event"] == "run_end"
    with pytest.raises(ValueError, match="No session entry"):
        find_entry(entries, "zzzz")
    with pytest.raises(ValueError, match="ambiguous"):
        find_entry(entries, "abcd")
