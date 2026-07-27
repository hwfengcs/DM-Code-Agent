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
from dm_agent.tools.base import Tool


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


def test_run_rejects_resume_with_reflexion(tmp_path):
    agent = ReactAgent(
        FakeRespondClient([]),
        _tools(),
        enable_planning=False,
        enable_compression=False,
        enable_reflexion=True,
    )
    with pytest.raises(ValueError):
        agent.run("task", checkpoint_path=tmp_path / "cp.json")
