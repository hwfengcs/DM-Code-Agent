"""End-to-end tests for observation truncation and the read-before-edit guard."""

from __future__ import annotations

import json
from pathlib import Path

from dm_agent.core.agent import ReactAgent
from dm_agent.core.events import EventBus
from dm_agent.tools.base import Tool
from dm_agent.tools.file_tools import create_file, edit_file, read_file
from dm_agent.tracing import TraceWriter, load_trace_events


class FakeRespondClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def respond(self, messages, **extra):
        self.requests.append((messages, extra))
        if not self.responses:
            raise AssertionError("FakeRespondClient ran out of responses")
        return self.responses.pop(0)


def _file_tools():
    return [
        Tool("read_file", "Read a file", read_file),
        Tool("create_file", "Create a file", create_file),
        Tool("edit_file", "Edit a file", edit_file),
        Tool("task_complete", "Finish", lambda arguments: "finished"),
    ]


def _action(action: str, action_input) -> str:
    return json.dumps(
        {"thought": "step", "action": action, "action_input": action_input},
        ensure_ascii=False,
    )


def test_edit_guard_blocks_unread_file_then_allows_after_read(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = Path("app.py")
    target.write_text("original line\n", encoding="utf-8")

    client = FakeRespondClient(
        [
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 1,
                    "line_end": 1,
                    "content": "hacked line",
                },
            ),
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 1,
                    "line_end": 1,
                    "content": "edited line",
                },
            ),
            _action("finish", "edited app.py after re-reading"),
        ]
    )
    agent = ReactAgent(client, _file_tools(), enable_planning=False, enable_compression=False)

    result = agent.run("edit app.py", max_steps=6)

    assert result["metadata"]["status"] == "success"
    assert result["metadata"]["edit_guard_block_count"] == 1
    blocked = result["steps"][0]["observation"]
    assert blocked.startswith("Edit blocked")
    # The blocked edit must not have touched the file.
    assert "hacked" not in Path("app.py").read_text(encoding="utf-8")
    assert Path("app.py").read_text(encoding="utf-8") == "edited line\n"
    # Guard text must not read as a failure (no replan / failure bookkeeping).
    assert not ReactAgent._is_failure_observation(blocked)


def test_edit_guard_requires_reread_after_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("one\ntwo\n", encoding="utf-8")
    trace_path = tmp_path / "trace.jsonl"

    client = FakeRespondClient(
        [
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 1,
                    "line_end": 1,
                    "content": "ONE",
                },
            ),
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 2,
                    "line_end": 2,
                    "content": "TWO",
                },
            ),
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 2,
                    "line_end": 2,
                    "content": "TWO",
                },
            ),
            _action("finish", "both lines updated"),
        ]
    )
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        client,
        _file_tools(),
        enable_planning=False,
        enable_compression=False,
        trace_writer=writer,
    )

    result = agent.run("edit app.py twice", max_steps=8)
    writer.close()

    assert result["metadata"]["status"] == "success"
    assert result["metadata"]["edit_guard_block_count"] == 1
    assert Path("app.py").read_text(encoding="utf-8") == "ONE\nTWO\n"
    guard_events = [e for e in load_trace_events(trace_path) if e["event"] == "edit_guard"]
    assert len(guard_events) == 1
    assert guard_events[0]["payload"]["reason"] == "stale_read"


def test_edit_guard_allows_consecutive_content_anchored_edits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("one\ntwo\n", encoding="utf-8")

    client = FakeRespondClient(
        [
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "one", "new_string": "ONE"},
            ),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "two", "new_string": "TWO"},
            ),
            _action("finish", "content edits complete"),
        ]
    )
    agent = ReactAgent(client, _file_tools(), enable_planning=False, enable_compression=False)

    result = agent.run("edit app.py twice by content", max_steps=6)

    assert result["metadata"]["edit_guard_block_count"] == 0
    assert Path("app.py").read_text(encoding="utf-8") == "ONE\nTWO\n"


def test_edit_guard_keeps_line_mode_stale_after_content_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("one\ntwo\n", encoding="utf-8")

    client = FakeRespondClient(
        [
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "one\n", "new_string": "zero\none\n"},
            ),
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 2,
                    "line_end": 2,
                    "content": "STALE",
                },
            ),
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 3,
                    "line_end": 3,
                    "content": "TWO",
                },
            ),
            _action("finish", "line edit completed after reread"),
        ]
    )
    agent = ReactAgent(client, _file_tools(), enable_planning=False, enable_compression=False)

    result = agent.run("mix content and line edits", max_steps=8)

    assert result["metadata"]["edit_guard_block_count"] == 1
    assert result["steps"][2]["observation"].startswith("Edit blocked")
    assert Path("app.py").read_text(encoding="utf-8") == "zero\none\nTWO\n"


def test_identity_edit_is_counted_without_advancing_write_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("one\n", encoding="utf-8")
    trace_path = tmp_path / "trace.jsonl"

    client = FakeRespondClient(
        [
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "one", "new_string": "one"},
            ),
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 1,
                    "line_end": 1,
                    "content": "ONE",
                },
            ),
            _action("finish", "identity edit skipped"),
        ]
    )
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        client,
        _file_tools(),
        enable_planning=False,
        enable_compression=False,
        trace_writer=writer,
    )

    result = agent.run("skip identity edit", max_steps=6)
    writer.close()

    assert result["metadata"]["edit_noop_count"] == 1
    assert result["metadata"]["edit_guard_block_count"] == 0
    assert result["metadata"]["backup_count"] == 1
    assert Path("app.py").read_text(encoding="utf-8") == "ONE\n"
    noop_events = [e for e in load_trace_events(trace_path) if e["event"] == "edit_noop"]
    assert len(noop_events) == 1
    assert noop_events[0]["payload"]["reason"] == "identical_content"
    backup_events = [e for e in load_trace_events(trace_path) if e["event"] == "file_backup"]
    assert len(backup_events) == 1


def test_identity_edit_does_not_complete_planned_edit_step(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("one\n", encoding="utf-8")

    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "read_file", "reason": "inspect"},
                        {"step": 2, "action": "edit_file", "reason": "change code"},
                        {"step": 3, "action": "task_complete", "reason": "finish"},
                    ]
                }
            ),
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "one", "new_string": "one"},
            ),
        ]
    )
    agent = ReactAgent(client, _file_tools(), enable_planning=True, enable_compression=False)

    result = agent.run("change app.py", max_steps=2)

    assert result["metadata"]["edit_noop_count"] == 1
    assert result["metadata"]["backup_count"] == 0
    assert agent.planner is not None
    assert agent.planner.current_plan[0].completed is True
    assert agent.planner.current_plan[1].completed is False
    assert agent.planner.get_next_step().action == "edit_file"


def test_identity_edit_keeps_existing_stale_state_for_later_line_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("one\ntwo\n", encoding="utf-8")

    client = FakeRespondClient(
        [
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "one", "new_string": "ONE"},
            ),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "two", "new_string": "two"},
            ),
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 2,
                    "line_end": 2,
                    "content": "TWO",
                },
            ),
            _action("finish", "stale state preserved"),
        ]
    )
    agent = ReactAgent(client, _file_tools(), enable_planning=False, enable_compression=False)

    result = agent.run("preserve stale state across no-op", max_steps=6)

    assert result["metadata"]["edit_noop_count"] == 1
    assert result["metadata"]["edit_guard_block_count"] == 1
    assert result["steps"][3]["observation"].startswith("Edit blocked")
    assert Path("app.py").read_text(encoding="utf-8") == "ONE\ntwo\n"


def test_edit_guard_blocks_unread_content_anchored_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("one\n", encoding="utf-8")

    client = FakeRespondClient(
        [
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "one", "new_string": "ONE"},
            ),
            _action("finish", "blind content edit blocked"),
        ]
    )
    agent = ReactAgent(client, _file_tools(), enable_planning=False, enable_compression=False)

    result = agent.run("try blind content edit", max_steps=3)

    assert result["metadata"]["edit_guard_block_count"] == 1
    assert result["steps"][0]["observation"].startswith("Edit blocked")
    assert Path("app.py").read_text(encoding="utf-8") == "one\n"


def test_explicit_no_progress_read_still_provides_edit_guard_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("one\n", encoding="utf-8")
    event_bus = EventBus()

    def declare_read_no_progress(event):
        if event.tool_name == "read_file":
            # 故意注入“无计划进展”信号，验证它不会抹掉实际发生的读取证据。
            # 正常成功的只读调用不应仅因没有持久化副作用就设置该字段。
            event.no_change = True
            event.no_change_reason = "forced_no_progress"

    event_bus.on("after_tool_result", declare_read_no_progress, name="declare_read_no_progress")
    client = FakeRespondClient(
        [
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 1,
                    "line_end": 1,
                    "content": "ONE",
                },
            ),
            _action("finish", "read evidence retained"),
        ]
    )
    agent = ReactAgent(
        client,
        _file_tools(),
        enable_planning=False,
        enable_compression=False,
        event_bus=event_bus,
    )

    result = agent.run("read then edit", max_steps=4)

    assert result["metadata"]["edit_guard_block_count"] == 0
    assert Path("app.py").read_text(encoding="utf-8") == "ONE\n"


def test_content_anchor_stale_bypass_does_not_apply_to_overridden_edit_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("one\n", encoding="utf-8")
    edit_calls = []

    def overridden_edit(arguments):
        edit_calls.append(dict(arguments))
        Path(arguments["path"]).write_text("extension write\n", encoding="utf-8")
        return "extension wrote file"

    tools = [
        Tool("read_file", "Read a file", read_file),
        Tool("edit_file", "Extension edit", overridden_edit),
        Tool("task_complete", "Finish", lambda arguments: "finished"),
    ]
    client = FakeRespondClient(
        [
            _action("read_file", {"path": "app.py"}),
            _action("edit_file", {"path": "app.py", "operation": "replace"}),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "extension", "new_string": "EXTENSION"},
            ),
            _action("finish", "override stayed guarded"),
        ]
    )
    agent = ReactAgent(client, tools, enable_planning=False, enable_compression=False)

    result = agent.run("guard overridden edit tool", max_steps=5)

    assert len(edit_calls) == 1
    assert result["metadata"]["edit_guard_block_count"] == 1
    assert result["steps"][2]["observation"].startswith("Edit blocked")


def test_edit_guard_disabled_allows_blind_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("original\n", encoding="utf-8")

    client = FakeRespondClient(
        [
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 1,
                    "line_end": 1,
                    "content": "blind edit",
                },
            ),
            _action("finish", "edited without reading"),
        ]
    )
    agent = ReactAgent(
        client,
        _file_tools(),
        enable_planning=False,
        enable_compression=False,
        enable_edit_guard=False,
    )

    result = agent.run("edit app.py", max_steps=4)

    assert result["metadata"]["edit_guard_block_count"] == 0
    assert Path("app.py").read_text(encoding="utf-8") == "blind edit\n"


def test_create_file_is_not_blocked_and_counts_as_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    client = FakeRespondClient(
        [
            _action("create_file", {"path": "new.py", "content": "a\nb\n"}),
            _action(
                "edit_file",
                {
                    "path": "new.py",
                    "operation": "replace",
                    "line_start": 1,
                    "line_end": 1,
                    "content": "A",
                },
            ),
            _action("read_file", {"path": "new.py"}),
            _action(
                "edit_file",
                {
                    "path": "new.py",
                    "operation": "replace",
                    "line_start": 1,
                    "line_end": 1,
                    "content": "A",
                },
            ),
            _action("finish", "created and edited new.py"),
        ]
    )
    agent = ReactAgent(client, _file_tools(), enable_planning=False, enable_compression=False)

    result = agent.run("create then edit", max_steps=6)

    # create_file is a write: the follow-up edit without a read gets blocked once.
    assert result["metadata"]["edit_guard_block_count"] == 1
    assert result["metadata"]["status"] == "success"
    assert Path("new.py").read_text(encoding="utf-8") == "A\nb\n"


def test_large_observation_is_truncated_in_history_and_trace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    trace_path = tmp_path / "trace.jsonl"
    big_output = "x" * 50000

    tools = [
        Tool("dump", "Dump output", lambda arguments: big_output),
        Tool("task_complete", "Finish", lambda arguments: "finished"),
    ]
    client = FakeRespondClient(
        [
            _action("dump", {}),
            _action("finish", "dumped and summarized the output"),
        ]
    )
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        client,
        tools,
        enable_planning=False,
        enable_compression=False,
        max_observation_chars=1000,
        trace_writer=writer,
    )

    result = agent.run("dump output", max_steps=4)
    writer.close()

    assert result["metadata"]["truncation_count"] == 1
    assert result["metadata"]["truncated_chars_saved"] > 0
    observation = result["steps"][0]["observation"]
    assert "[truncated: showing first" in observation
    assert len(observation) < 1000 + 400  # bounded content plus marker overhead
    # History and trace carry the same bounded text.
    history_entry = next(
        message["content"]
        for message in agent.conversation_history
        if "[truncated:" in message.get("content", "")
    )
    assert observation in history_entry
    events = load_trace_events(trace_path)
    truncation_events = [e for e in events if e["event"] == "observation_truncated"]
    assert len(truncation_events) == 1
    assert truncation_events[0]["payload"]["original_chars"] == 50000
    tool_calls = [e for e in events if e["event"] == "tool_call"]
    dump_calls = [e for e in tool_calls if e["payload"]["action"] == "dump"]
    assert dump_calls
    assert all("[truncated:" in e["payload"]["observation"] for e in dump_calls)


def test_truncation_disabled_with_zero_cap(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    big_output = "y" * 20000
    tools = [
        Tool("dump", "Dump output", lambda arguments: big_output),
        Tool("task_complete", "Finish", lambda arguments: "finished"),
    ]
    client = FakeRespondClient(
        [
            _action("dump", {}),
            _action("finish", "kept full output"),
        ]
    )
    agent = ReactAgent(
        client,
        tools,
        enable_planning=False,
        enable_compression=False,
        max_observation_chars=0,
    )

    result = agent.run("dump output", max_steps=4)

    assert result["metadata"]["truncation_count"] == 0
    assert result["steps"][0]["observation"] == big_output


def test_token_budget_forces_early_compression(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    big = "z" * 400  # ~100 estimated tokens per observation
    tools = [
        Tool("dump", "Dump output", lambda arguments: big),
        Tool("task_complete", "Finish", lambda arguments: "finished"),
    ]
    responses = [_action("dump", {}) for _ in range(4)]
    responses.append(_action("finish", "done after heavy output"))
    client = FakeRespondClient(responses)
    agent = ReactAgent(
        client,
        tools,
        enable_planning=False,
        enable_compression=True,
        context_token_budget=120,
        max_observation_chars=0,
    )
    assert agent.compressor is not None
    # Shrink the verbatim window so old messages become compressible quickly;
    # cadence stays high so only the token budget can trigger compression.
    agent.compressor.keep_recent = 1
    agent.compressor.compress_every = 50

    result = agent.run("dump repeatedly", max_steps=8)

    assert result["metadata"]["status"] == "success"
    assert result["metadata"]["budget_compression_count"] >= 1
    assert agent.compressor.last_trigger in {"token_budget", ""}


def test_edit_creates_backup_of_original_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("precious original\n", encoding="utf-8")

    client = FakeRespondClient(
        [
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {
                    "path": "app.py",
                    "operation": "replace",
                    "line_start": 1,
                    "line_end": 1,
                    "content": "overwritten",
                },
            ),
            _action("finish", "edited with backup"),
        ]
    )
    agent = ReactAgent(client, _file_tools(), enable_planning=False, enable_compression=False)

    result = agent.run("edit app.py", max_steps=4)

    assert result["metadata"]["backup_count"] == 1
    backup_dir = Path(result["metadata"]["backup_dir"])
    assert backup_dir.is_dir()
    backups = list(backup_dir.glob("*-app.py"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "precious original\n"
    # Cleanup the temp backup dir created by this test run.
    import shutil

    shutil.rmtree(backup_dir, ignore_errors=True)
