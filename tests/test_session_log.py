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
    find_entry_index,
    load_session_entries,
    message_entries,
    normalize_entries,
    rebuild_context,
    summarize_events,
)


class FakeRespondClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.model = "fake-model"
        self.requests = []

    def respond(self, messages, **extra):
        self.requests.append([dict(message) for message in messages])
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


def test_parse_failed_response_is_audited_but_omitted_from_later_context(tmp_path):
    trace_path = tmp_path / "parse-error.jsonl"
    raw = "not-json-" + "x" * 31000
    client = FakeRespondClient([raw, _action("finish", {"answer": "recovered"})])
    writer = TraceWriter(trace_path, capture_llm_io=True)
    agent = ReactAgent(
        client,
        _tools(),
        enable_planning=False,
        enable_compression=False,
        trace_writer=writer,
    )

    result = agent.run("recover after a huge parse failure", max_steps=3)
    writer.close()

    assert result["final_answer"] == "recovered"
    assert result["metadata"]["parse_error_context_omitted_count"] == 1
    assert result["metadata"]["parse_error_context_omitted_chars"] == len(raw)
    second_request = client.requests[1]
    assert all(message.get("content") != raw for message in second_request)
    assert any("omitted from context" in message.get("content", "") for message in second_request)

    entries = load_session_entries(trace_path)
    parse_error = next(entry for entry in entries if entry["event"] == "parse_error")
    assert "omitted from context" in parse_error["payload"]["context_replacement"]
    assistant_messages = [
        entry["payload"]
        for entry in message_entries(entries)
        if entry["payload"].get("role") == "assistant"
    ]
    assert assistant_messages[0]["content"] == raw

    rebuilt = rebuild_context(entries, apply_compaction=False)
    assert all(message.get("content") != raw for message in rebuilt)
    assert any("omitted from context" in message.get("content", "") for message in rebuilt)


def test_legacy_parse_error_without_replacement_keeps_original_context():
    entries = normalize_entries(
        [
            {"event": "run_start", "payload": {}},
            {
                "event": "message",
                "payload": {
                    "role": "assistant",
                    "kind": "model_response",
                    "content": "legacy malformed response",
                },
            },
            {
                "event": "parse_error",
                "payload": {"response_chars": 25, "error": "legacy parse failure"},
            },
        ]
    )

    assert rebuild_context(entries, apply_compaction=False) == [
        {"role": "assistant", "content": "legacy malformed response"}
    ]


def test_short_parse_failed_response_is_also_replaced_in_context(tmp_path):
    raw = "not-json"
    client = FakeRespondClient([raw, _action("finish", {"answer": "recovered"})])
    agent = ReactAgent(
        client,
        _tools(),
        enable_planning=False,
        enable_compression=False,
    )

    result = agent.run("recover from a short parse failure", max_steps=3)

    assert result["metadata"]["parse_error_context_omitted_count"] == 1
    assert result["metadata"]["parse_error_context_omitted_chars"] == len(raw)
    assert all(message.get("content") != raw for message in client.requests[1])
    assert any(
        "omitted from context" in message.get("content", "") for message in client.requests[1]
    )


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


def test_rebuild_context_uses_only_entries_after_the_latest_run_start(tmp_path):
    trace_path = tmp_path / "multiple-runs.jsonl"
    writer = TraceWriter(trace_path, capture_llm_io=True)
    agent = ReactAgent(
        FakeRespondClient(
            [_action("finish", {"answer": "first"}), _action("finish", {"answer": "second"})]
        ),
        _tools(),
        enable_planning=False,
        enable_compression=False,
        trace_writer=writer,
    )

    agent.run("first task", max_steps=1)
    agent.reset_conversation()
    agent.run("second task", max_steps=1)
    writer.close()

    entries = load_session_entries(trace_path)
    compacted = rebuild_context(entries, apply_compaction=True)
    full = rebuild_context(entries, apply_compaction=False)
    assert compacted == full
    assert any("second task" in message["content"] for message in full)
    assert all("first task" not in message["content"] for message in full)


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


# --- 7.1 checkpoint 退化成「记住某个 entry id」 ----------------------------


def _stalled_run(checkpoint_path, *, max_steps=3):
    """跑到步数上限就停下的一轮，用来制造可续跑的 checkpoint。"""
    agent = ReactAgent(
        FakeRespondClient(
            [_action("echo", {"text": f"turn {index}"}) for index in range(max_steps)]
        ),
        _tools(),
        enable_planning=False,
        enable_compression=False,
    )
    return agent.run(
        "echo until the step limit", max_steps=max_steps, checkpoint_path=checkpoint_path
    )


def test_session_checkpoint_appends_one_entry_per_step(tmp_path):
    checkpoint_path = tmp_path / "run.jsonl"

    result = _stalled_run(checkpoint_path)

    assert result["metadata"]["status"] == "max_steps_exceeded"
    entries = load_session_entries(checkpoint_path)
    checkpoints = [entry for entry in entries if entry["event"] == "checkpoint"]
    # 每步开头一条 + 步数耗尽的终态一条，append-only 全部留着。
    assert [entry["payload"]["step_number"] for entry in checkpoints] == [0, 1, 2, 3]
    assert all(entry["payload"]["state"]["task"] for entry in checkpoints)


def _checkpoint_compaction_run(checkpoint_path, *, trace_path=None):
    responses = [_action("echo", {"text": f"turn {index}"}) for index in range(12)]
    responses.append(_action("finish", {"answer": "done"}))
    writer = TraceWriter(trace_path) if trace_path is not None else None
    agent = ReactAgent(
        FakeRespondClient(responses),
        _tools(),
        enable_planning=False,
        enable_compression=True,
        context_token_budget=60,
        trace_writer=writer,
    )
    result = agent.run(
        "echo many times with a complete checkpoint session",
        max_steps=20,
        checkpoint_path=checkpoint_path,
    )
    if writer is not None:
        writer.close()
    return result


def test_checkpoint_only_jsonl_contains_a_complete_viewable_session(tmp_path):
    checkpoint_path = tmp_path / "run.jsonl"

    result = _checkpoint_compaction_run(checkpoint_path)
    entries = load_session_entries(checkpoint_path)
    events = [entry["event"] for entry in entries]

    assert result["metadata"]["status"] == "success"
    assert "message" in events
    assert "step" in events
    assert "compaction" in events
    assert "checkpoint" in events
    assert summarize_events(entries)["step_count"] > 0


def test_trace_and_checkpoint_fanout_preserves_fidelity_and_local_compaction_ids(tmp_path):
    trace_path = tmp_path / "run.trace.jsonl"
    checkpoint_path = tmp_path / "run.checkpoint.jsonl"

    _checkpoint_compaction_run(checkpoint_path, trace_path=trace_path)
    trace_entries = load_session_entries(trace_path)
    checkpoint_entries = load_session_entries(checkpoint_path)
    trace_messages = message_entries(trace_entries)
    checkpoint_messages = message_entries(checkpoint_entries)

    assert len(trace_messages) == len(checkpoint_messages)
    assert [(entry["payload"]["role"], entry["payload"]["kind"]) for entry in trace_messages] == [
        (entry["payload"]["role"], entry["payload"]["kind"]) for entry in checkpoint_messages
    ]
    assert trace_messages[0]["id"] != checkpoint_messages[0]["id"]

    trace_assistant = [
        entry["payload"] for entry in trace_messages if entry["payload"]["role"] == "assistant"
    ]
    checkpoint_assistant = [
        entry["payload"] for entry in checkpoint_messages if entry["payload"]["role"] == "assistant"
    ]
    assert all(
        "content" not in payload and payload["content_sha256"] for payload in trace_assistant
    )
    assert all(payload["content"] for payload in checkpoint_assistant)

    for entries in (trace_entries, checkpoint_entries):
        ids = [entry["id"] for entry in entries]
        message_ids = {entry["id"] for entry in message_entries(entries)}
        assert len(ids) == len(set(ids))
        assert entries[0]["parent_id"] == ""
        assert all(
            entries[index]["parent_id"] == entries[index - 1]["id"]
            for index in range(1, len(entries))
        )
        for compaction in (entry["payload"] for entry in entries if entry["event"] == "compaction"):
            assert compaction["first_kept_entry_id"] in message_ids
            assert set(compaction["folded_entry_ids"]) <= message_ids

    assert not [entry for entry in trace_entries if entry["event"] == "checkpoint"]
    assert [entry for entry in checkpoint_entries if entry["event"] == "checkpoint"]


def test_checkpoint_session_sink_failure_warns_and_does_not_abort_the_run(tmp_path, capsys):
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("occupied", encoding="utf-8")
    checkpoint_path = blocked_parent / "run.jsonl"
    agent = ReactAgent(
        FakeRespondClient([_action("finish", {"answer": "done"})]),
        _tools(),
        enable_planning=False,
        enable_compression=False,
    )

    result = agent.run("checkpoint failure is best effort", checkpoint_path=checkpoint_path)

    assert result["metadata"]["status"] == "success"
    assert capsys.readouterr().out.count("checkpoint 会话写入失败") == 1


def test_resume_from_a_session_checkpoint_continues_the_run(tmp_path):
    from dm_agent.core.persistence import load_resume_state

    checkpoint_path = tmp_path / "run.jsonl"
    _stalled_run(checkpoint_path)

    resume_state = load_resume_state(checkpoint_path)
    agent = ReactAgent(
        FakeRespondClient([_action("finish", {"answer": "resumed and finished"})]),
        _tools(),
        enable_planning=False,
        enable_compression=False,
    )
    result = agent.run(resume_state.task, max_steps=6, resume_state=resume_state)

    assert resume_state.step_count == 3
    assert result["metadata"]["status"] == "success"
    assert result["final_answer"] == "resumed and finished"
    assert result["metadata"]["resumed_from_step"] == 3


def test_resume_at_selects_an_earlier_checkpoint_entry(tmp_path):
    from dm_agent.core.persistence import load_resume_state

    checkpoint_path = tmp_path / "run.jsonl"
    _stalled_run(checkpoint_path)
    entries = load_session_entries(checkpoint_path)
    checkpoints = [entry for entry in entries if entry["event"] == "checkpoint"]

    picked = load_resume_state(checkpoint_path, at=checkpoints[1]["id"])

    assert picked.step_count == 1
    # 不指定 --resume-at 时取最后一条，语义与老快照一致。
    assert load_resume_state(checkpoint_path).step_count == 3


def test_resume_still_reads_the_legacy_json_snapshot(tmp_path):
    from dm_agent.core.persistence import load_resume_state

    checkpoint_path = tmp_path / "cp.json"
    _stalled_run(checkpoint_path)

    resume_state = load_resume_state(checkpoint_path)

    assert checkpoint_path.read_text(encoding="utf-8").lstrip().startswith("{")
    assert resume_state.step_count == 3
    with pytest.raises(ValueError, match="--resume-at"):
        load_resume_state(checkpoint_path, at="abcd-0001")


def test_resume_reports_a_session_without_checkpoint_entries(tmp_path):
    from dm_agent.core.persistence import load_resume_state

    trace_path = tmp_path / "session.jsonl"
    _run_agent(trace_path, [_action("finish", {"answer": "done"})], enable_compression=False)

    with pytest.raises(ValueError, match="No resumable checkpoint entry"):
        load_resume_state(trace_path)


def test_trace_and_checkpoint_may_not_share_one_file():
    from dm_agent.cli.args import parse_args, validate_feature_args

    args = parse_args(["task", "--trace", "same.jsonl", "--checkpoint", "same.jsonl"])

    assert "不能指向同一个文件" in validate_feature_args(args)


# --- 7.3 fork -------------------------------------------------------------


def test_fork_copies_entries_up_to_the_fork_point_and_appends_a_fork_entry(tmp_path):
    from dm_agent.tracing import fork_session

    checkpoint_path = tmp_path / "run.jsonl"
    _stalled_run(checkpoint_path)
    entries = load_session_entries(checkpoint_path)
    at = [entry for entry in entries if entry["event"] == "checkpoint"][1]["id"]

    result = fork_session(entries, source=checkpoint_path, at=at)

    forked = load_session_entries(result["output"])
    assert result["forked_from_entry_id"] == at
    fork_index = find_entry_index(entries, at)
    assert [entry["id"] for entry in forked[:-1]] == [
        entry["id"] for entry in entries[: fork_index + 1]
    ]
    assert forked[-1]["event"] == "fork"
    # fork 条目的 parent_id 指回分叉点，两份 JSONL 由此串成一棵树。
    assert forked[-1]["parent_id"] == at
    # fork 条目走的是常规脱敏路径，所以 source 里的家目录会被写成 ~（与 run_start.cwd 一致）。
    assert forked[-1]["payload"]["source"].endswith("run.jsonl")
    assert result["resumable_checkpoint_entry_id"] == at
    assert result["resumable_step_number"] == 1


def test_forked_session_can_be_resumed_and_finished(tmp_path):
    from dm_agent.core.persistence import load_resume_state
    from dm_agent.tracing import fork_session

    checkpoint_path = tmp_path / "run.jsonl"
    _stalled_run(checkpoint_path)
    entries = load_session_entries(checkpoint_path)
    at = [entry for entry in entries if entry["event"] == "checkpoint"][1]["id"]
    forked = fork_session(entries, source=checkpoint_path, at=at)["output"]

    resume_state = load_resume_state(forked)
    agent = ReactAgent(
        FakeRespondClient([_action("finish", {"answer": "finished on the branch"})]),
        _tools(),
        enable_planning=False,
        enable_compression=False,
    )
    result = agent.run(resume_state.task, max_steps=4, resume_state=resume_state)

    # 分叉点在第 1 步，所以新分支从第 2 步继续，而不是从原会话的第 3 步。
    assert resume_state.step_count == 1
    assert result["metadata"]["resumed_from_step"] == 1
    assert result["metadata"]["status"] == "success"
    assert result["final_answer"] == "finished on the branch"


def test_fork_refuses_to_overwrite_and_reports_unknown_entries(tmp_path):
    from dm_agent.tracing import fork_session

    checkpoint_path = tmp_path / "run.jsonl"
    _stalled_run(checkpoint_path)
    entries = load_session_entries(checkpoint_path)
    at = entries[1]["id"]
    output = tmp_path / "branch.jsonl"
    fork_session(entries, source=checkpoint_path, at=at, output=output)

    with pytest.raises(ValueError, match="Refusing to overwrite"):
        fork_session(entries, source=checkpoint_path, at=at, output=output)
    with pytest.raises(ValueError, match="No session entry"):
        fork_session(entries, source=checkpoint_path, at="nope-9999")


def test_fork_works_on_a_legacy_trace_but_says_it_cannot_be_resumed(tmp_path, capsys):
    from dm_agent.tracing.cli import main as trace_main

    legacy_path = tmp_path / "legacy.jsonl"
    legacy_path.write_text(
        "\n".join(
            json.dumps(entry, ensure_ascii=False)
            for entry in [
                {"timestamp": "t0", "run_id": "r", "event": "run_start", "payload": {"task": "x"}},
                {
                    "timestamp": "t1",
                    "run_id": "r",
                    "event": "step",
                    "payload": {"step_number": 1, "action": "echo", "observation": "o"},
                },
                {
                    "timestamp": "t2",
                    "run_id": "r",
                    "event": "run_end",
                    "payload": {"status": "success", "final_answer": "done", "metadata": {}},
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert trace_main(["fork", str(legacy_path), "--at", "legacy-0001"]) == 0

    output = capsys.readouterr().out
    assert "legacy-0001" in output
    assert "not resumed" in output
    assert (tmp_path / "legacy.fork-legacy-0001.jsonl").is_file()


def test_legacy_traces_still_work_with_view_analyze_and_replay(tmp_path):
    from dm_agent.tracing.cli import main as trace_main

    legacy_path = tmp_path / "legacy.jsonl"
    legacy_path.write_text(
        "\n".join(
            json.dumps(entry, ensure_ascii=False)
            for entry in [
                {
                    "timestamp": "t0",
                    "run_id": "r",
                    "event": "run_start",
                    "payload": {"schema_version": "1.0", "task": "legacy"},
                },
                {
                    "timestamp": "t1",
                    "run_id": "r",
                    "event": "run_end",
                    "payload": {"status": "success", "final_answer": "done", "metadata": {}},
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert trace_main(["view", str(legacy_path), "--json"]) == 0
    assert trace_main(["analyze", str(legacy_path), "--json"]) == 0
    assert trace_main(["replay", str(legacy_path)]) == 0
