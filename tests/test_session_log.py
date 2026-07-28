"""会话日志的条目结构、非破坏式压缩、resume 与 fork 的测试。

这些用例全部不依赖 API key：模型响应由 ``FakeRespondClient`` 按脚本给出，
因此「开/关压缩跑同一任务，原始条目序列逐位一致」这类断言是确定性的。
"""

from __future__ import annotations

import json

import pytest

from dm_agent.core.agent import ReactAgent
from dm_agent.memory.context_compressor import ContextCompressor, apply_compaction
from dm_agent.tools.base import Tool
from dm_agent.tracing import (
    TraceWriter,
    load_session_entries,
    message_entries,
    normalize_entries,
    rebuild_context,
)


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


# --- 7.2 压缩非破坏化 ------------------------------------------------------


def _legacy_compress(compressor, history):
    """改造前 ``ContextCompressor.compress`` 的算法，逐字节对照用。

    保留这份参考实现是为了钉住「非破坏化没有改变发给 LLM 的消息」这一条：
    折叠决策与消息重建拆开之后，输出必须与老实现完全一致。
    """
    if not history:
        return []
    system_messages = [msg for msg in history if msg.get("role") == "system"]
    non_system = [msg for msg in history if msg.get("role") != "system"]
    recent_count = compressor.keep_recent * 2
    recent = non_system[-recent_count:] if len(non_system) > recent_count else list(non_system)
    older = non_system[:-recent_count] if len(non_system) > recent_count else []
    if older:
        compressor.memory.add_messages(
            older,
            scope=compressor.scope,
            turn=1,
            invalidate_on_success=compressor.enable_hygiene,
        )
    query = "\n".join(message.get("content", "") for message in recent[-4:])
    block = compressor.memory.render(
        query, scope=compressor.scope, limit=compressor.memory_limit, turn=1
    )
    memory_messages = [{"role": "user", "content": block}] if block else []
    return system_messages + memory_messages + recent


def _long_history(turns=24):
    history = [{"role": "user", "content": "任务：修复 module.py 里的失败测试"}]
    for index in range(turns):
        history.append({"role": "assistant", "content": f"assistant turn {index}"})
        history.append({"role": "user", "content": f"观察：module.py 第 {index} 次运行 error"})
    return history


def test_plan_and_apply_compaction_reproduce_the_legacy_compress_output():
    history = _long_history()
    reference = _legacy_compress(ContextCompressor(compress_every=2, keep_recent=8), history)

    planned = ContextCompressor(compress_every=2, keep_recent=8).plan_compaction(history)
    wrapped = ContextCompressor(compress_every=2, keep_recent=8).compress(history)

    assert apply_compaction(history, planned) == reference
    assert wrapped == reference


def test_compaction_describes_the_folded_range_without_dropping_messages():
    history = _long_history()
    compressor = ContextCompressor(compress_every=2, keep_recent=8)

    compaction = compressor.plan_compaction(history)

    assert compaction.first_kept_index == len(history) - 16
    assert compaction.folded_indexes == tuple(range(len(history) - 16))
    assert len(history) == 49  # 原始历史一条没少
    assert set(compaction.folded_indexes).isdisjoint({compaction.first_kept_index})


def _compaction_run(trace_path, *, enable_compression):
    """跑同一份脚本任务；只有压缩开关不同。"""
    responses = [_action("echo", {"text": f"turn {index}"}) for index in range(12)]
    responses.append(_action("finish", {"answer": "done"}))
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        FakeRespondClient(responses),
        _tools(),
        enable_planning=False,
        enable_compression=enable_compression,
        context_token_budget=60,
        trace_writer=writer,
    )
    result = agent.run("echo many times then finish", max_steps=20)
    writer.close()
    return result


def _message_signature(entries):
    return [
        (
            entry["payload"]["role"],
            entry["payload"]["kind"],
            entry["payload"].get("content", entry["payload"].get("content_sha256")),
        )
        for entry in message_entries(entries)
    ]


def test_compression_leaves_the_original_entry_sequence_bit_identical(tmp_path):
    on_path = tmp_path / "on.jsonl"
    off_path = tmp_path / "off.jsonl"

    _compaction_run(on_path, enable_compression=True)
    _compaction_run(off_path, enable_compression=False)

    on_entries = load_session_entries(on_path)
    off_entries = load_session_entries(off_path)
    compactions = [entry for entry in on_entries if entry["event"] == "compaction"]

    # 唯一的差异只能是 compaction 条目本身。
    assert compactions
    assert not [entry for entry in off_entries if entry["event"] == "compaction"]
    assert _message_signature(on_entries) == _message_signature(off_entries)


def test_compaction_entry_points_at_surviving_message_entries(tmp_path):
    trace_path = tmp_path / "session.jsonl"
    _compaction_run(trace_path, enable_compression=True)

    entries = load_session_entries(trace_path)
    message_ids = {entry["id"] for entry in message_entries(entries)}
    compaction = next(entry for entry in entries if entry["event"] == "compaction")["payload"]

    assert compaction["first_kept_entry_id"] in message_ids
    assert compaction["folded_entry_ids"]
    # 被折叠的条目**一条不删**：每个 id 都还能在会话日志里找到。
    assert set(compaction["folded_entry_ids"]) <= message_ids
    assert (
        compaction["folded_message_count"] + compaction["kept_message_count"]
        >= compaction["original_message_count"]
    )


def test_rebuild_context_can_replay_with_and_without_compaction(tmp_path):
    trace_path = tmp_path / "session.jsonl"
    _compaction_run(trace_path, enable_compression=True)
    entries = load_session_entries(trace_path)

    compacted = rebuild_context(entries, apply_compaction=True)
    full = rebuild_context(entries, apply_compaction=False)

    assert len(full) > len(compacted)
    assert len(full) == len(message_entries(entries))
    # 同一份会话日志既能复现真正发出去的窗口，也能复现「假装从没压缩过」的全量历史。
    assert full[-1] == compacted[-1]
