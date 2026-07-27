"""生命周期事件总线的端到端语义测试。"""

from __future__ import annotations

import json

from dm_agent.core import EventBus, ReactAgent
from dm_agent.tools.base import Tool
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


def _action(action: str, action_input) -> str:
    return json.dumps(
        {"thought": "step", "action": action, "action_input": action_input},
        ensure_ascii=False,
    )


def exploding_handler(event):
    event.arguments["poisoned"] = True
    raise RuntimeError("boom")


def test_before_tool_call_block_prevents_execution_and_returns_reason():
    calls = []
    bus = EventBus()

    def block_shell(event):
        if event.tool_name == "run_shell":
            return {"block": True, "reason": "策略拒绝执行危险命令"}
        return None

    bus.on("before_tool_call", block_shell, name="block_shell")
    client = FakeRespondClient(
        [_action("run_shell", {"command": "rm -rf /tmp/demo"}), _action("finish", "done")]
    )
    agent = ReactAgent(
        client,
        [Tool("run_shell", "Run shell", lambda arguments: calls.append(arguments) or "ran")],
        enable_planning=False,
        enable_compression=False,
        event_bus=bus,
    )

    result = agent.run("run command", max_steps=2)

    assert calls == []
    assert result["steps"][0]["observation"] == "策略拒绝执行危险命令"
    assert result["metadata"]["status"] == "success"


def test_after_tool_result_handlers_chain_in_registration_order():
    second_seen = []
    bus = EventBus()

    def append_first(event):
        return event.observation + "|first"

    def append_second(event):
        second_seen.append(event.observation)
        return event.observation + "|second"

    bus.on("after_tool_result", append_first, name="append_first")
    bus.on("after_tool_result", append_second, name="append_second")
    client = FakeRespondClient([_action("echo", {}), _action("finish", "done")])
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: "raw")],
        enable_planning=False,
        enable_compression=False,
        event_bus=bus,
    )

    result = agent.run("echo", max_steps=2)

    assert second_seen == ["raw|first"]
    assert result["steps"][0]["observation"] == "raw|first|second"


def test_handler_exception_is_isolated_and_traced(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    tool_calls = []
    bus = EventBus()
    bus.on("before_tool_call", exploding_handler, name="exploding_handler")
    client = FakeRespondClient([_action("echo", {}), _action("finish", "done")])
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: tool_calls.append(arguments) or "ok")],
        enable_planning=False,
        enable_compression=False,
        trace_writer=writer,
        event_bus=bus,
    )

    result = agent.run("echo", max_steps=2)
    writer.close()

    hook_errors = [
        event for event in load_trace_events(trace_path) if event["event"] == "hook_error"
    ]
    assert result["metadata"]["status"] == "success"
    assert tool_calls == [{}]
    assert len(hook_errors) == 1
    assert hook_errors[0]["payload"]["hook"] == "before_tool_call"
    assert hook_errors[0]["payload"]["handler"] == "exploding_handler"
    assert hook_errors[0]["payload"]["handler_position"] == 1
    assert hook_errors[0]["payload"]["step_number"] == 1
    assert hook_errors[0]["payload"]["tool_name"] == "echo"
    assert hook_errors[0]["payload"]["error_type"] == "RuntimeError"


def test_before_llm_request_rewrites_actual_messages():
    bus = EventBus()

    def add_context(event):
        return [*event.messages, {"role": "user", "content": "hook sentinel"}]

    bus.on("before_llm_request", add_context, name="add_context")
    client = FakeRespondClient([_action("finish", "done")])
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: "unused")],
        enable_planning=False,
        enable_compression=False,
        event_bus=bus,
    )

    agent.run("finish", max_steps=1)

    sent_messages, _extra = client.requests[0]
    assert sent_messages[-1] == {"role": "user", "content": "hook sentinel"}


def test_before_llm_request_covers_planner_and_agent_phases():
    phases = []
    bus = EventBus()

    def note_phase(event):
        phases.append(event.phase)

    bus.on("before_llm_request", note_phase, name="note_phase")
    client = FakeRespondClient([json.dumps({"plan": []}), _action("finish", "done")])
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: "unused")],
        enable_planning=True,
        enable_compression=False,
        event_bus=bus,
    )

    agent.run("finish", max_steps=1)

    assert phases == ["planner", "agent"]


def test_before_tool_call_can_modify_arguments_in_place_without_revalidation():
    received = []
    bus = EventBus()

    def rewrite_arguments(event):
        event.arguments["value"] = "rewritten"

    bus.on("before_tool_call", rewrite_arguments, name="rewrite_arguments")
    client = FakeRespondClient([_action("echo", {"value": "original"}), _action("finish", "done")])
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: received.append(dict(arguments)) or "ok")],
        enable_planning=False,
        enable_compression=False,
        event_bus=bus,
    )

    result = agent.run("rewrite", max_steps=2)

    assert received == [{"value": "rewritten"}]
    assert result["steps"][0]["action_input"] == {"value": "rewritten"}
