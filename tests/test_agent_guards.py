"""End-to-end tests for observation truncation and the read-before-edit guard."""

from __future__ import annotations

import json
from pathlib import Path

from dm_agent.core.agent import ReactAgent
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
