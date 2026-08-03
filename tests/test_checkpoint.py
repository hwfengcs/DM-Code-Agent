"""Tests for run-level checkpoint/resume."""

from __future__ import annotations

import json

import pytest

from dm_agent.core.agent import ReactAgent
from dm_agent.core.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION,
    RunCheckpoint,
    load_checkpoint,
    save_checkpoint,
)
from dm_agent.core.run_state import RunContext
from dm_agent.memory import ContextCompressor
from dm_agent.memory.context_budget import estimate_messages_tokens
from dm_agent.memory.context_compressor import Compaction, apply_compaction
from dm_agent.tools.base import Tool
from dm_agent.tracing import TraceWriter, load_trace_events, rebuild_context


class FakeRespondClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.model = "fake-model"

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


def _tools(log=None):
    def echo(arguments):
        if log is not None:
            log.append(arguments.get("text", ""))
        return f"echo:{arguments.get('text', '')}"

    return [
        Tool("echo", "Echo text", echo),
        Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
    ]


def test_checkpoint_roundtrip_and_schema_guard(tmp_path):
    path = tmp_path / "cp.json"
    checkpoint = RunCheckpoint(
        task="demo task",
        step_count=2,
        conversation_history=[{"role": "user", "content": "任务：demo task"}],
        steps=[{"thought": "t", "action": "echo", "action_input": {}, "observation": "o"}],
        metadata={"status": "running", "tool_error_count": 1},
        plan=[{"step_number": 1, "action": "echo", "reason": "r", "completed": True}],
    )
    save_checkpoint(path, checkpoint)

    loaded = load_checkpoint(path)
    assert loaded.task == "demo task"
    assert loaded.step_count == 2
    assert loaded.metadata["tool_error_count"] == 1
    assert loaded.plan[0]["completed"] is True
    assert loaded.schema_version == CHECKPOINT_SCHEMA_VERSION
    # Atomic write leaves no temp residue.
    assert [p.name for p in tmp_path.iterdir()] == ["cp.json"]


def test_load_checkpoint_rejects_unknown_version_and_garbage(tmp_path):
    bad_version = tmp_path / "bad_version.json"
    bad_version.write_text(
        json.dumps({"schema_version": 999, "task": "x", "step_count": 0}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_checkpoint(bad_version)

    garbage = tmp_path / "garbage.json"
    garbage.write_text("not json at all", encoding="utf-8")
    with pytest.raises(ValueError):
        load_checkpoint(garbage)

    with pytest.raises(ValueError):
        load_checkpoint(tmp_path / "missing.json")


def test_agent_writes_checkpoint_on_max_steps(tmp_path):
    checkpoint_path = tmp_path / "run.json"
    client = FakeRespondClient(
        [
            _action("echo", {"text": "one"}),
            _action("echo", {"text": "two"}),
        ]
    )
    agent = ReactAgent(
        client,
        _tools(),
        enable_planning=False,
        enable_compression=False,
    )

    result = agent.run("echo twice then stop", max_steps=2, checkpoint_path=checkpoint_path)

    assert result["metadata"]["status"] == "max_steps_exceeded"
    checkpoint = load_checkpoint(checkpoint_path)
    assert checkpoint.step_count == 2
    assert checkpoint.task == "echo twice then stop"
    assert len(checkpoint.steps) == 2
    assert checkpoint.metadata["status"] == "max_steps_exceeded"
    assert checkpoint.agent_config["max_steps"] == 2


def test_agent_resumes_from_checkpoint_and_finishes(tmp_path):
    checkpoint_path = tmp_path / "run.json"
    first_log = []
    first_client = FakeRespondClient(
        [
            _action("echo", {"text": "one"}),
            _action("echo", {"text": "two"}),
        ]
    )
    first_agent = ReactAgent(
        first_client,
        _tools(first_log),
        enable_planning=False,
        enable_compression=False,
    )
    first_result = first_agent.run("echo then finish", max_steps=2, checkpoint_path=checkpoint_path)
    assert first_result["metadata"]["status"] == "max_steps_exceeded"
    assert first_log == ["one", "two"]

    checkpoint = load_checkpoint(checkpoint_path)
    second_log = []
    second_client = FakeRespondClient(
        [
            _action("finish", "resumed and finished the task"),
        ]
    )
    second_agent = ReactAgent(
        second_client,
        _tools(second_log),
        enable_planning=False,
        enable_compression=False,
    )
    result = second_agent.run(
        checkpoint.task,
        max_steps=4,
        resume_state=checkpoint,
    )

    assert result["metadata"]["status"] == "success"
    assert result["final_answer"] == "resumed and finished the task"
    # Prior steps are preserved and no tools re-ran on resume.
    assert len(result["steps"]) == 3
    assert result["steps"][0]["action"] == "echo"
    assert second_log == []
    assert result["metadata"]["resumed_from_step"] == 2
    # Restored history contains the original task prompt from the first run.
    history_texts = [m.get("content", "") for m in second_agent.conversation_history]
    assert any("echo then finish" in text for text in history_texts)


def test_resume_reuses_exact_history_without_synthesizing_previous_steps():
    history = [
        {"role": "user", "content": "任务：resume exactly"},
        {"role": "assistant", "content": _action("echo", {"text": "one"})},
        {"role": "user", "content": "观察：echo:one"},
    ]
    checkpoint = RunCheckpoint(
        task="resume exactly",
        step_count=1,
        conversation_history=history,
        steps=[
            {
                "thought": "step",
                "action": "echo",
                "action_input": {"text": "one"},
                "observation": "echo:one",
            }
        ],
    )
    client = FakeRespondClient([_action("finish", "resumed")])
    agent = ReactAgent(
        client,
        _tools(),
        enable_planning=False,
        enable_compression=False,
    )

    agent.run(checkpoint.task, max_steps=3, resume_state=checkpoint)

    assert client.requests[0][1:] == history
    assert all("之前的步骤：" not in message["content"] for message in client.requests[0])


def test_resume_restores_compressor_memory(tmp_path):
    checkpoint_path = tmp_path / "run.json"
    client = FakeRespondClient(
        [
            _action("echo", {"text": "inspect retry.py"}),
            _action("echo", {"text": "observe pytest failed in retry.py"}),
            _action("echo", {"text": "three"}),
        ]
    )
    agent = ReactAgent(
        client,
        _tools(),
        enable_planning=False,
        enable_compression=True,
    )
    assert agent.compressor is not None
    agent.compressor.compress_every = 1
    agent.compressor.keep_recent = 1

    agent.run("build up memory", max_steps=3, checkpoint_path=checkpoint_path)
    checkpoint = load_checkpoint(checkpoint_path)
    assert checkpoint.compressor_state is not None
    saved_items = len(checkpoint.compressor_state["memory"]["items"])
    assert saved_items > 0

    resumed_agent = ReactAgent(
        FakeRespondClient([_action("finish", "done after resume")]),
        _tools(),
        enable_planning=False,
        enable_compression=True,
    )
    resumed_agent.run(checkpoint.task, max_steps=5, resume_state=checkpoint)

    assert resumed_agent.compressor is not None
    assert resumed_agent.compressor.memory_count == saved_items


def test_resume_restores_sticky_compaction_and_reuses_it_for_the_next_request(tmp_path):
    trace_path = tmp_path / "sticky-trace.jsonl"
    history = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"message {index} app.py " + "x" * 100,
        }
        for index in range(18)
    ]
    sticky = Compaction(
        first_kept_index=4,
        folded_indexes=(0, 1, 2, 3),
        summary="<agent_memory>remember app.py</agent_memory>",
        trigger="cadence",
        estimated_tokens=500,
        memory_items=1,
    )
    compressor = ContextCompressor()
    compressor.accept_beneficial_compaction(sticky)
    checkpoint = RunCheckpoint(
        task="resume sticky context",
        step_count=0,
        conversation_history=history,
        compressor_state=compressor.export_state(),
    )
    checkpoint_path = tmp_path / "sticky.json"
    save_checkpoint(checkpoint_path, checkpoint)
    loaded = load_checkpoint(checkpoint_path)
    client = FakeRespondClient([_action("finish", "done")])
    writer = TraceWriter(trace_path, capture_llm_io=True)
    agent = ReactAgent(
        client,
        _tools(),
        enable_planning=False,
        enable_compression=True,
        trace_writer=writer,
    )

    agent.run(loaded.task, max_steps=2, resume_state=loaded)
    writer.close()

    assert agent.compressor is not None
    assert agent.compressor.last_beneficial_compaction == sticky
    assert client.requests[0][1:] == apply_compaction(history, sticky)
    events = load_trace_events(trace_path)
    compaction = next(event for event in events if event["event"] == "compaction")
    payload = compaction["payload"]
    assert payload["phase"] == "sticky_reuse"
    assert payload["trigger"] == "sticky_reuse"
    assert payload["estimated_tokens_before"] == estimate_messages_tokens(history)
    assert payload["estimated_tokens_after"] == estimate_messages_tokens(
        apply_compaction(history, sticky)
    )
    assert payload["memory_items"] == agent.compressor.memory_count
    assert rebuild_context(events, until_entry_id=compaction["id"]) == client.requests[0][1:]


def test_resume_without_compressor_state_clears_existing_compressor_state():
    checkpoint = RunCheckpoint(
        task="legacy resume without compressor state",
        step_count=0,
        conversation_history=[{"role": "user", "content": "legacy task"}],
        compressor_state=None,
    )
    agent = ReactAgent(
        FakeRespondClient([_action("finish", "done")]),
        _tools(),
        enable_planning=False,
        enable_compression=True,
    )
    assert agent.compressor is not None
    agent.compressor.memory.add("stale memory")
    agent.compressor.accept_beneficial_compaction(
        Compaction(
            first_kept_index=1,
            folded_indexes=(0,),
            summary="<agent_memory>stale</agent_memory>",
        )
    )

    agent.run(checkpoint.task, max_steps=1, resume_state=checkpoint)

    assert agent.compressor.memory_count == 0
    assert agent.compressor.last_beneficial_compaction is None


def test_resume_restores_plan(tmp_path):
    trace_path = tmp_path / "resume-plan.jsonl"
    checkpoint = RunCheckpoint(
        task="resume with plan",
        step_count=1,
        conversation_history=[{"role": "user", "content": "任务：resume with plan"}],
        steps=[
            {
                "thought": "t",
                "action": "echo",
                "action_input": {"text": "one"},
                "observation": "echo:one",
            }
        ],
        plan=[
            {
                "step_number": 1,
                "action": "echo",
                "reason": "first",
                "completed": True,
                "result": "echo:one",
            },
            {"step_number": 2, "action": "task_complete", "reason": "finish"},
        ],
    )
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        FakeRespondClient([_action("finish", "resumed with a restored plan")]),
        _tools(),
        enable_planning=True,
        enable_compression=False,
        trace_writer=writer,
    )
    result = agent.run(checkpoint.task, max_steps=4, resume_state=checkpoint)
    writer.close()

    assert result["metadata"]["status"] == "success"
    assert agent.planner is not None
    # 计划连同完成状态一起回到 planner，resume 后不会重跑已完成的步骤。
    assert [step.action for step in agent.planner.current_plan] == ["echo", "task_complete"]
    assert agent.planner.current_plan[0].completed is True

    events = load_trace_events(trace_path)
    assert any(event["event"] == "run_start" for event in events)
    assert any(event["event"] == "run_end" for event in events)


def test_resume_warns_on_config_mismatch(capsys):
    checkpoint = RunCheckpoint(
        task="resume with a different config",
        step_count=0,
        agent_config={
            "temperature": 0.9,
            "model": "other-model",
            "enable_planning": True,
        },
    )
    agent = ReactAgent(
        FakeRespondClient([_action("finish", "resumed anyway")]),
        _tools(),
        enable_planning=False,
        enable_compression=False,
        temperature=0.0,
    )

    agent.run(checkpoint.task, max_steps=2, resume_state=checkpoint)

    out = capsys.readouterr().out
    assert "[warn] resume 配置不一致：temperature checkpoint=0.9 当前=0.0" in out
    assert "[warn] resume 配置不一致：model checkpoint=other-model 当前=fake-model" in out
    assert "[warn] resume 配置不一致：enable_planning checkpoint=True 当前=False" in out


def test_checkpoint_save_failure_warns_and_keeps_running(tmp_path, capsys):
    # 父路径是普通文件，落盘时 mkdir 必然抛 OSError（跨平台一致）。
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    agent = ReactAgent(
        FakeRespondClient([_action("finish", "finished despite a failed checkpoint")]),
        _tools(),
        enable_planning=False,
        enable_compression=False,
    )

    result = agent.run(
        "survive checkpoint failure", max_steps=1, checkpoint_path=blocker / "cp.json"
    )

    assert result["metadata"]["status"] == "success"
    assert "[warn] checkpoint 保存失败" in capsys.readouterr().out


def test_checkpoint_save_is_recorded_in_trace(tmp_path):
    trace_path = tmp_path / "checkpoint.jsonl"
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        FakeRespondClient([_action("finish", "done")]),
        _tools(),
        enable_planning=False,
        enable_compression=False,
        trace_writer=writer,
    )

    agent.run("record the checkpoint", max_steps=1, checkpoint_path=tmp_path / "cp.json")
    writer.close()

    saved = [
        event for event in load_trace_events(trace_path) if event["event"] == "checkpoint_saved"
    ]
    assert saved
    assert saved[0]["payload"]["step_number"] == 0


def test_backup_is_skipped_when_write_arguments_have_no_path(tmp_path):
    tools = [
        Tool("create_file", "Create", lambda arguments: f"created:{arguments.get('path', '')}"),
        Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
    ]
    agent = ReactAgent(
        FakeRespondClient([_action("create_file", {"content": "x"}), _action("finish", "done")]),
        tools,
        enable_planning=False,
        enable_compression=False,
    )

    result = agent.run("write without a path", max_steps=3)

    assert result["metadata"]["backup_count"] == 0
    assert result["metadata"]["backup_dir"] == ""


def test_backup_ignores_non_object_arguments():
    agent = ReactAgent(
        FakeRespondClient([]),
        _tools(),
        enable_planning=False,
        enable_compression=False,
    )
    metadata = {"backup_count": 0, "backup_dir": ""}
    context = RunContext(run_id="run-id", step_number=1, metadata=metadata)

    agent._persistence.backup_before_write("not a dict", context)

    assert metadata == {"backup_count": 0, "backup_dir": ""}
