"""生命周期事件总线的端到端语义测试。"""

from __future__ import annotations

import json

from dm_agent.core import EventBus, ReactAgent
from dm_agent.memory.context_compressor import Compaction, Mem0StyleMemory
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


def test_before_finish_block_rejects_completion_and_agent_continues():
    bus = EventBus()
    seen = []

    def reject_first(event):
        seen.append((event.action, event.completion_text))
        if len(seen) == 1:
            return {"block": True, "reason": "门禁否决：还没跑测试"}
        return None

    bus.on("before_finish", reject_first, name="reject_first")
    client = FakeRespondClient([_action("finish", "first"), _action("finish", "second")])
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: "unused")],
        enable_planning=False,
        enable_compression=False,
        event_bus=bus,
    )

    result = agent.run("finish twice", max_steps=2)

    assert [action for action, _text in seen] == ["finish", "finish"]
    assert result["steps"][0]["observation"] == "门禁否决：还没跑测试"
    assert result["final_answer"] == "second"
    assert result["metadata"]["status"] == "success"


def test_on_run_start_suffix_is_appended_to_system_prompt_each_attempt():
    bus = EventBus()
    attempts = []

    def inject(event):
        attempts.append(event.attempt)
        event.metadata["demo_capability_enabled"] = True
        return f"<hint attempt={event.attempt}>"

    bus.on("on_run_start", inject, name="inject")
    client = FakeRespondClient([_action("finish", "done")])
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: "unused")],
        enable_planning=False,
        enable_compression=False,
        event_bus=bus,
    )

    result = agent.run("finish", max_steps=1)

    assert attempts == [1]
    assert result["metadata"]["demo_capability_enabled"] is True
    assert "<hint attempt=1>" in client.requests[0][0][0]["content"]


def test_on_run_end_retry_reruns_with_clean_history():
    bus = EventBus()
    history_sizes = []

    def retry_once(event):
        history_sizes.append(len(event.result["steps"]))
        return {"retry": True} if event.attempt == 1 else None

    bus.on("on_run_end", retry_once, name="retry_once")
    client = FakeRespondClient(
        [_action("echo", {}), _action("echo", {}), _action("finish", "second attempt")]
    )
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: "ok")],
        max_steps=1,
        enable_planning=False,
        enable_compression=False,
        event_bus=bus,
    )

    result = agent.run("retry me", max_steps=2)

    # 第一轮用光 2 步，第二轮从干净历史重新开始，只用了 1 步。
    assert history_sizes == [2, 1]
    assert result["final_answer"] == "second attempt"
    assert result["metadata"]["trial"] == 2
    second_attempt_messages = client.requests[2][0]
    assert not any("观察" in message["content"] for message in second_attempt_messages)


def test_on_run_end_retry_discards_sticky_compaction_from_failed_attempt():
    bus = EventBus()
    client = FakeRespondClient([_action("finish", "first"), _action("finish", "second")])
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: "ok")],
        enable_planning=False,
        enable_compression=True,
        event_bus=bus,
    )

    def retry_with_failed_sticky(event):
        if event.attempt != 1:
            return None
        assert agent.compressor is not None
        agent.compressor.accept_beneficial_compaction(
            Compaction(
                first_kept_index=1,
                folded_indexes=(0,),
                summary="<agent_memory>failed-attempt-only</agent_memory>",
            )
        )
        return {"retry": True}

    bus.on("on_run_end", retry_with_failed_sticky, name="retry_with_failed_sticky")

    result = agent.run("retry without stale sticky", max_steps=1)

    assert result["final_answer"] == "second"
    assert not any("failed-attempt-only" in message["content"] for message in client.requests[1][0])


def test_on_run_end_retry_restores_full_compressor_state_after_real_compaction():
    class TrackingMemory(Mem0StyleMemory):
        def __init__(self):
            super().__init__()
            self.render_count = 0

        def render(self, query, **kwargs):
            self.render_count += 1
            return super().render(query, **kwargs)

        def capture_rollback_state(self):
            return {
                "base": super().capture_rollback_state(),
                "render_count": self.render_count,
            }

        def restore_rollback_state(self, state):
            super().restore_rollback_state(state["base"])
            self.render_count = state["render_count"]

    bus = EventBus()
    client = FakeRespondClient([_action("finish", "first"), _action("finish", "second")])
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: "ok")],
        enable_planning=False,
        enable_compression=True,
        event_bus=bus,
    )
    assert agent.compressor is not None
    memory = TrackingMemory()
    agent.compressor.memory = memory
    agent.compressor.compress_every = 1
    agent.compressor.keep_recent = 1
    agent.compressor.token_budget = 0
    agent.conversation_history = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"carried message {index} app.py " + "x" * 180,
        }
        for index in range(16)
    ]

    def retry_first_attempt(event):
        return {"retry": True} if event.attempt == 1 else None

    bus.on("on_run_end", retry_first_attempt, name="retry_first_attempt")

    result = agent.run("retry after a real compaction", max_steps=1)

    first_request = client.requests[0][0]
    second_request = client.requests[1][0]
    assert result["final_answer"] == "second"
    assert first_request == second_request
    assert any(message["content"].startswith("<agent_memory>") for message in first_request[1:])
    assert agent.compressor.export_state()["compression_count"] == 1
    assert memory.render_count == 1


def test_run_hook_exception_is_isolated_and_traced(tmp_path):
    trace_path = tmp_path / "run-hooks.jsonl"
    bus = EventBus()

    def exploding_run_end(event):
        raise RuntimeError("run hook boom")

    bus.on("on_run_end", exploding_run_end, name="exploding_run_end")
    client = FakeRespondClient([_action("finish", "done")])
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        client,
        [Tool("echo", "Echo", lambda arguments: "unused")],
        enable_planning=False,
        enable_compression=False,
        trace_writer=writer,
        event_bus=bus,
    )

    result = agent.run("finish", max_steps=1)
    writer.close()

    hook_errors = [
        event for event in load_trace_events(trace_path) if event["event"] == "hook_error"
    ]
    assert result["metadata"]["status"] == "success"
    assert len(hook_errors) == 1
    assert hook_errors[0]["payload"]["hook"] == "on_run_end"
