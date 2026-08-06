from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from dm_agent.core import ReactAgent
from dm_agent.core.capabilities import CapabilityContext
from dm_agent.core.events import (
    AfterToolResultEvent,
    BeforeToolCallEvent,
    EventBus,
    RunStartEvent,
)
from dm_agent.tools.base import Tool
from dm_agent.tools.file_tools import create_file, edit_file, read_file
from dm_agent.tracing import TraceWriter, load_trace_events
from swebench_verified import predict
from swebench_verified.progress_guard import SWEProgressLoopGuard


class _FakeAgent:
    result: dict[str, Any] | Exception
    last_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, *_args: Any, **kwargs: Any) -> None:
        type(self).last_kwargs = kwargs

    def run(self, _prompt: str) -> dict[str, Any]:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _instance() -> dict[str, Any]:
    return {
        "instance_id": "owner__repo-1",
        "repo": "owner/repo",
        "base_commit": "abc123",
        "problem_statement": "fix it",
        "difficulty": "easy",
    }


def _prepare_predict(monkeypatch, tmp_path: Path, result: dict[str, Any] | Exception) -> Path:
    workspace_root = tmp_path / "workspaces"

    def materialize(_instance_id: str, destination: Path) -> Path:
        destination.mkdir(parents=True)
        return destination

    _FakeAgent.result = result
    monkeypatch.setattr(predict, "materialize_workspace", materialize)
    monkeypatch.setattr(predict, "build_client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(predict, "ReactAgent", _FakeAgent)
    monkeypatch.setattr(predict, "default_tools", lambda **_kwargs: [])
    monkeypatch.setattr(predict, "extract_patch", lambda _workspace: "diff --git a/a b/a\n")
    return workspace_root


def test_predict_one_exports_empty_patch_diagnostics(monkeypatch, tmp_path):
    metadata = {
        "status": "max_steps",
        "replan_count": 2,
        "parse_error_count": 3,
        "parse_repair_count": 4,
        "parse_error_context_omitted_count": 5,
        "parse_error_context_omitted_chars": 600,
        "truncation_count": 7,
        "edit_guard_block_count": 8,
        "edit_noop_count": 9,
        "repeat_search_block_count": 10,
        "edit_state_revisit_count": 11,
        "edit_cycle_block_count": 12,
    }
    workspace_root = _prepare_predict(
        monkeypatch,
        tmp_path,
        {"metadata": metadata, "steps": [{}, {}]},
    )

    record = predict.predict_one(
        _instance(),
        workspace_root=workspace_root,
        provider="deepseek",
        model=None,
        max_steps=60,
        temperature=0.0,
        timeout=30,
        trace_dir=None,
        keep_workspace=True,
    )

    assert record["dm_diagnostics_version"] == 1
    assert record["dm_steps"] == 2
    assert record["dm_replans"] == 2
    assert record["dm_parse_errors"] == 3
    assert record["dm_parse_repairs"] == 4
    assert record["dm_parse_error_context_omitted_count"] == 5
    assert record["dm_parse_error_context_omitted_chars"] == 600
    assert record["dm_truncations"] == 7
    assert record["dm_edit_guard_blocks"] == 8
    assert record["dm_edit_noops"] == 9
    assert record["dm_repeat_search_blocks"] == 10
    assert record["dm_edit_state_revisits"] == 11
    assert record["dm_edit_cycle_blocks"] == 12
    capabilities = _FakeAgent.last_kwargs["capabilities"]
    assert len(capabilities) == 1
    assert isinstance(capabilities[0], SWEProgressLoopGuard)


def test_predict_one_marks_diagnostics_unmeasured_after_agent_exception(monkeypatch, tmp_path):
    workspace_root = _prepare_predict(monkeypatch, tmp_path, RuntimeError("boom"))

    record = predict.predict_one(
        _instance(),
        workspace_root=workspace_root,
        provider="deepseek",
        model=None,
        max_steps=60,
        temperature=0.0,
        timeout=30,
        trace_dir=None,
        keep_workspace=True,
    )

    assert record["dm_status"] == "agent_exception"
    assert record["dm_patch_chars"] > 0
    assert "dm_diagnostics_version" not in record
    assert "dm_parse_errors" not in record
    assert "dm_repeat_search_blocks" not in record
    assert "dm_edit_cycle_blocks" not in record


def _event_bus_with_progress_guard(trace_writer=None):
    bus = EventBus()
    guard = SWEProgressLoopGuard()
    guard.install(
        CapabilityContext(
            event_bus=bus,
            client_for=lambda _phase: None,
            trace_writer=trace_writer,
        )
    )
    return bus


def _run_guarded_write(
    bus: EventBus,
    metadata: dict[str, Any],
    *,
    tool_name: str,
    arguments: dict[str, Any],
    step_number: int,
    runner: Callable[[dict[str, Any]], str],
    content_anchor_safe: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    event = BeforeToolCallEvent(
        tool_name=tool_name,
        arguments=dict(arguments),
        step_number=step_number,
        run_id="run",
        metadata=metadata,
        content_anchor_safe=content_anchor_safe,
    )
    block = bus.emit_before_tool_call(event)
    if block is not None:
        return block, None
    observation = runner(event.arguments)
    final_observation = bus.emit_after_tool_result(
        AfterToolResultEvent(
            tool_name=tool_name,
            arguments=event.arguments,
            observation=observation,
            step_number=step_number,
            run_id="run",
            tool_succeeded=True,
            metadata=metadata,
        )
    )
    return None, final_observation


def _seed_content_edit_revisit(bus: EventBus, metadata: dict[str, Any]) -> None:
    for step_number, old_string, new_string in [(1, "A", "B"), (2, "B", "A")]:
        block, _ = _run_guarded_write(
            bus,
            metadata,
            tool_name="edit_file",
            arguments={
                "path": "app.py",
                "old_string": old_string,
                "new_string": new_string,
            },
            step_number=step_number,
            runner=edit_file,
            content_anchor_safe=True,
        )
        assert block is None


def test_repeat_search_guard_replays_cache_and_invalidates_on_file_change(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "pkg" / "mod.py"
    target.parent.mkdir()
    target.write_text("def target():\n    return 1\n", encoding="utf-8")
    trace_path = tmp_path / "repeat-search.jsonl"
    writer = TraceWriter(trace_path)
    bus = _event_bus_with_progress_guard(writer)
    metadata: dict[str, Any] = {}
    suffix = bus.emit_run_start(
        RunStartEvent(
            task="fix",
            attempt=1,
            run_id="run",
            prompt_suffix="existing suffix",
            metadata=metadata,
        )
    )
    arguments = {"path": "pkg/mod.py", "pattern": "def target"}

    first = BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 1, "run", metadata)
    assert bus.emit_before_tool_call(first) is None
    bus.emit_after_tool_result(
        AfterToolResultEvent(
            tool_name=_SEARCH_ACTION,
            arguments=dict(arguments),
            observation="found at line 10",
            step_number=1,
            run_id="run",
            tool_succeeded=True,
            metadata=metadata,
        )
    )

    repeated = BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 2, "run", metadata)
    block = bus.emit_before_tool_call(repeated)

    assert suffix == "existing suffix"
    assert block is not None and block["block"] is True
    assert "step 1" in block["reason"]
    assert "> found at line 10" in block["reason"]
    assert metadata["progress_loop_guard_enabled"] is True
    assert metadata["repeat_search_block_count"] == 1

    # 无论改写来自哪个工具，只要目标文件内容变化，同一搜索就重新放行。
    target.write_text("def target():\n    return 2\n", encoding="utf-8")
    assert (
        bus.emit_before_tool_call(
            BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 3, "run", metadata)
        )
        is None
    )
    writer.close()

    events = load_trace_events(trace_path)
    repeat_events = [event for event in events if event["event"] == "swebench_repeat_search_block"]
    assert len(repeat_events) == 1
    assert repeat_events[0]["payload"]["first_success_step"] == 1


def test_repeat_search_guard_replays_full_bounded_observation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("mod.py").write_text("target = 1\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))
    arguments = {"path": "mod.py", "pattern": "target"}
    observation = "x" * 2000 + "\nLATE_MATCH_EVIDENCE"
    bus.emit_after_tool_result(
        AfterToolResultEvent(
            tool_name=_SEARCH_ACTION,
            arguments=dict(arguments),
            observation=observation,
            step_number=1,
            run_id="run",
            tool_succeeded=True,
            metadata=metadata,
        )
    )

    block = bus.emit_before_tool_call(
        BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 2, "run", metadata)
    )

    assert block is not None
    assert "LATE_MATCH_EVIDENCE" in block["reason"]


def test_repeat_search_guard_does_not_cache_failed_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))
    arguments = {"path": "missing.py", "pattern": "target"}
    bus.emit_after_tool_result(
        AfterToolResultEvent(
            tool_name=_SEARCH_ACTION,
            arguments=dict(arguments),
            observation="文件 missing.py 不存在。",
            step_number=1,
            run_id="run",
            tool_succeeded=True,
            metadata=metadata,
        )
    )

    assert (
        bus.emit_before_tool_call(
            BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 2, "run", metadata)
        )
        is None
    )


def test_repeat_search_trace_failure_does_not_change_block_decision(tmp_path, monkeypatch):
    class BrokenTrace:
        def record(self, _event, _payload):
            raise OSError("disk unavailable")

    monkeypatch.chdir(tmp_path)
    target = tmp_path / "mod.py"
    target.write_text("target = 1\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard(BrokenTrace())
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))
    arguments = {"path": "mod.py", "pattern": "target"}
    bus.emit_after_tool_result(
        AfterToolResultEvent(
            tool_name=_SEARCH_ACTION,
            arguments=dict(arguments),
            observation="found",
            step_number=1,
            run_id="run",
            tool_succeeded=True,
            metadata=metadata,
        )
    )

    block = bus.emit_before_tool_call(
        BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 2, "run", metadata)
    )

    assert block is not None and block["block"] is True
    assert metadata["repeat_search_block_count"] == 1


def test_edit_cycle_prediction_requires_canonical_valid_content_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("A\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))
    _seed_content_edit_revisit(bus, metadata)

    create_with_extra_edit_keys = BeforeToolCallEvent(
        tool_name="create_file",
        arguments={
            "path": "app.py",
            "content": "C\n",
            "old_string": "A",
            "new_string": "B",
        },
        step_number=3,
        run_id="run",
        metadata=metadata,
    )
    conflicting_edit_modes = BeforeToolCallEvent(
        tool_name="edit_file",
        arguments={
            "path": "app.py",
            "old_string": "A",
            "new_string": "B",
            "operation": "replace",
            "line_start": 1,
            "line_end": 1,
            "content": "C",
        },
        step_number=4,
        run_id="run",
        metadata=metadata,
        content_anchor_safe=True,
    )
    noncanonical_edit_tool = BeforeToolCallEvent(
        tool_name="edit_file",
        arguments={"path": "app.py", "old_string": "A", "new_string": "B"},
        step_number=5,
        run_id="run",
        metadata=metadata,
        content_anchor_safe=False,
    )

    assert bus.emit_before_tool_call(create_with_extra_edit_keys) is None
    assert bus.emit_before_tool_call(conflicting_edit_modes) is None
    assert bus.emit_before_tool_call(noncanonical_edit_tool) is None
    assert metadata["edit_cycle_block_count"] == 0


def test_edit_cycle_prediction_supports_omitted_new_string_deletion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("xy\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))

    first_block, _ = _run_guarded_write(
        bus,
        metadata,
        tool_name="edit_file",
        arguments={"path": "app.py", "old_string": "y"},
        step_number=1,
        runner=edit_file,
        content_anchor_safe=True,
    )
    undo_block, undo_observation = _run_guarded_write(
        bus,
        metadata,
        tool_name="edit_file",
        arguments={"path": "app.py", "old_string": "x", "new_string": "xy"},
        step_number=2,
        runner=edit_file,
        content_anchor_safe=True,
    )
    repeated_delete = BeforeToolCallEvent(
        tool_name="edit_file",
        arguments={"path": "app.py", "old_string": "y"},
        step_number=3,
        run_id="run",
        metadata=metadata,
        content_anchor_safe=True,
    )

    assert first_block is None
    assert undo_block is None
    assert undo_observation is not None
    assert "will be skipped before execution" in undo_observation
    block = bus.emit_before_tool_call(repeated_delete)
    assert block is not None and block["block"] is True
    assert Path("app.py").read_text(encoding="utf-8") == "xy\n"
    assert metadata["edit_cycle_block_count"] == 1


def test_line_number_edit_revisits_are_diagnostic_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("A\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))
    actions = [
        {"path": "app.py", "operation": "replace", "line_start": 1, "line_end": 1, "content": "B"},
        {"path": "app.py", "operation": "replace", "line_start": 1, "line_end": 1, "content": "A"},
        {"path": "app.py", "operation": "replace", "line_start": 1, "line_end": 1, "content": "B"},
    ]

    observations: list[str] = []
    for step_number, arguments in enumerate(actions, start=1):
        block, observation = _run_guarded_write(
            bus,
            metadata,
            tool_name="edit_file",
            arguments=arguments,
            step_number=step_number,
            runner=edit_file,
            content_anchor_safe=True,
        )
        assert block is None
        assert observation is not None
        observations.append(observation)

    assert "diagnostics only" in observations[1]
    assert "will be skipped" not in observations[1]
    assert metadata["edit_state_revisit_count"] == 2
    assert metadata["edit_cycle_block_count"] == 0


def test_create_file_revisits_are_diagnostic_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("A\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))

    observations: list[str] = []
    for step_number, content in enumerate(["B\n", "A\n", "B\n"], start=1):
        block, observation = _run_guarded_write(
            bus,
            metadata,
            tool_name="create_file",
            arguments={"path": "app.py", "content": content},
            step_number=step_number,
            runner=create_file,
        )
        assert block is None
        assert observation is not None
        observations.append(observation)

    assert "diagnostics only" in observations[1]
    assert "will be skipped" not in observations[1]
    assert metadata["edit_state_revisit_count"] == 2
    assert metadata["edit_cycle_block_count"] == 0


class _ScriptedClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    def respond(self, _messages, **_extra):
        return self.responses.pop(0)


def _action(action: str, action_input: Any) -> str:
    return json.dumps(
        {"thought": "step", "action": action, "action_input": action_input},
        ensure_ascii=False,
    )


_SEARCH_ACTION = "search_in_file"


def test_progress_loop_guard_breaks_scripted_search_fixed_point(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "pkg" / "mod.py"
    target.parent.mkdir()
    target.write_text("target = 1\n", encoding="utf-8")
    calls: list[dict[str, Any]] = []
    client = _ScriptedClient(
        [
            _action(_SEARCH_ACTION, {"path": "pkg/mod.py", "pattern": "target"}),
            _action(_SEARCH_ACTION, {"path": "pkg/mod.py", "pattern": "target"}),
            _action("finish", "done"),
        ]
    )
    agent = ReactAgent(
        client,
        [
            Tool(
                _SEARCH_ACTION,
                "search",
                lambda arguments: calls.append(dict(arguments)) or "found",
            )
        ],
        enable_planning=False,
        enable_compression=False,
        capabilities=[SWEProgressLoopGuard()],
    )

    result = agent.run("fix", max_steps=3)

    assert len(calls) == 1
    assert result["metadata"]["repeat_search_block_count"] == 1
    assert result["steps"][1]["observation"].startswith("Skipped exact duplicate search #1")


def test_progress_loop_guard_allows_one_undo_then_blocks_edit_cycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("value = 1\n", encoding="utf-8")
    client = _ScriptedClient(
        [
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "value = 1", "new_string": "value = 2"},
            ),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "value = 2", "new_string": "value = 1"},
            ),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "value = 1", "new_string": "value = 2"},
            ),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "value = 1", "new_string": "value = 3"},
            ),
            _action("finish", "done"),
        ]
    )
    agent = ReactAgent(
        client,
        [
            Tool("read_file", "read", read_file),
            Tool("edit_file", "edit", edit_file),
        ],
        enable_planning=False,
        enable_compression=False,
        capabilities=[SWEProgressLoopGuard()],
    )

    result = agent.run("fix", max_steps=6)

    assert Path("app.py").read_text(encoding="utf-8") == "value = 3\n"
    assert result["metadata"]["edit_state_revisit_count"] == 1
    assert result["metadata"]["edit_cycle_block_count"] == 1
    assert "Edit-state revisit #1" in result["steps"][2]["observation"]
    assert result["steps"][3]["observation"].startswith("Skipped edit-state cycle #1")
