import json

import pytest

from dm_agent.core.agent import ReactAgent
from dm_agent.core.planner import AdaptiveReplanPolicy
from dm_agent.core.planner import TaskPlanner
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


def test_task_planner_parses_json_inside_text():
    client = FakeRespondClient(
        [
            'Plan:\n{"plan": ['
            '{"step": 1, "action": "read_file", "reason": "inspect input"},'
            '{"step": 2, "action": "task_complete", "reason": "finish"}'
            "]}"
        ]
    )
    tools = [
        Tool("read_file", "Read a file", lambda arguments: "content"),
        Tool("task_complete", "Finish", lambda arguments: "done"),
    ]

    planner = TaskPlanner(client, tools)
    plan = planner.plan("inspect a file")

    assert [step.action for step in plan] == ["read_file", "task_complete"]
    assert planner.get_next_step().action == "read_file"
    planner.mark_completed(1, "ok")
    assert planner.get_next_step().action == "task_complete"


def test_react_agent_can_finish_without_tool_call():
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "thought": "The answer is ready.",
                    "action": "finish",
                    "action_input": {"answer": "done"},
                }
            )
        ]
    )
    agent = ReactAgent(
        client,
        [Tool("task_complete", "Finish", lambda arguments: "finished")],
        enable_planning=False,
        enable_compression=False,
    )

    result = agent.run("finish immediately")

    assert result["final_answer"] == "done"
    assert result["steps"][0]["action"] == "finish"
    assert result["metadata"]["status"] == "success"


def test_react_agent_executes_tool_then_finishes():
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "thought": "Use the echo tool.",
                    "action": "echo",
                    "action_input": {"text": "hello"},
                }
            ),
            json.dumps(
                {
                    "thought": "The tool result is enough.",
                    "action": "finish",
                    "action_input": "completed",
                }
            ),
        ]
    )
    tool = Tool("echo", "Echo text", lambda arguments: f"echo:{arguments['text']}")
    agent = ReactAgent(
        client,
        [tool, Tool("task_complete", "Finish", lambda arguments: "finished")],
        enable_planning=False,
        enable_compression=False,
    )

    result = agent.run("echo hello")

    assert result["final_answer"] == "completed"
    assert [step["action"] for step in result["steps"]] == ["echo", "finish"]
    assert "echo:hello" in result["steps"][0]["observation"]
    assert result["metadata"]["tool_error_count"] == 0


def test_react_agent_rejects_empty_task():
    agent = ReactAgent(
        FakeRespondClient([]),
        [Tool("task_complete", "Finish", lambda arguments: "finished")],
        enable_planning=False,
        enable_compression=False,
    )

    with pytest.raises(ValueError):
        agent.run(" ")


def test_react_agent_repairs_common_json_drift():
    client = FakeRespondClient(
        [
            "{'thought': 'single quotes', 'action': 'finish', "
            "'action_input': {'answer': 'repaired'},}"
        ]
    )
    agent = ReactAgent(
        client,
        [Tool("task_complete", "Finish", lambda arguments: "finished")],
        enable_planning=False,
        enable_compression=False,
    )

    result = agent.run("repair json")

    assert result["final_answer"] == "repaired"
    assert result["metadata"]["parse_repair_count"] == 1


def test_react_agent_replans_after_tool_failure():
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "explode", "reason": "trigger failure"},
                        {"step": 2, "action": "task_complete", "reason": "finish"},
                    ]
                }
            ),
            json.dumps(
                {
                    "thought": "Try the failing tool.",
                    "action": "explode",
                    "action_input": {},
                }
            ),
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "task_complete", "reason": "recover"},
                    ]
                }
            ),
            json.dumps(
                {
                    "thought": "Recover.",
                    "action": "task_complete",
                    "action_input": {"message": "recovered"},
                }
            ),
        ]
    )
    agent = ReactAgent(
        client,
        [
            Tool("explode", "Fail", lambda arguments: (_ for _ in ()).throw(RuntimeError("boom"))),
            Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
        ],
        enable_planning=True,
        enable_compression=False,
    )

    result = agent.run("recover from failure")

    assert result["final_answer"] == "recovered"
    assert result["metadata"]["tool_error_count"] == 1
    assert result["metadata"]["replan_count"] == 1


def test_adaptive_replan_policy_classifies_failure_signals():
    policy = AdaptiveReplanPolicy()

    tool_signal = policy.classify("Tool execution failed: boom", action="run_shell")
    parse_signal = policy.classify("Agent response parse failed: Response is not valid JSON")
    test_signal = policy.classify("pytest returncode: 1\nAssertionError")

    assert tool_signal.kind == "tool_error"
    assert tool_signal.strategy == "simplify_plan_skip_failed_tool"
    assert parse_signal.kind == "parse_error"
    assert parse_signal.strategy == "repair_response_format"
    assert test_signal.kind == "test_failure"
    assert test_signal.strategy == "inject_test_failure_context"


def test_adaptive_replan_policy_repeated_failure_experiment_is_default_off():
    policy = AdaptiveReplanPolicy()
    signal = policy.classify("Tool execution failed: boom", action="run_shell")

    default_decision = policy.decide(
        signal,
        replan_count=0,
        max_replans=-1,
        repeated_failure=True,
    )
    experiment_decision = policy.decide(
        signal,
        replan_count=0,
        max_replans=-1,
        repeated_failure=True,
        use_repeated_failure_escape=True,
    )

    assert default_decision.strategy == "simplify_plan_skip_failed_tool"
    assert experiment_decision.strategy == "break_repeated_failure_loop"
    assert experiment_decision.should_replan is True


def test_react_agent_adaptive_replan_records_strategy_metadata():
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "explode", "reason": "trigger failure"},
                        {"step": 2, "action": "task_complete", "reason": "finish"},
                    ]
                }
            ),
            json.dumps(
                {
                    "thought": "Try the failing tool.",
                    "action": "explode",
                    "action_input": {},
                }
            ),
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "task_complete", "reason": "recover"},
                    ]
                }
            ),
            json.dumps(
                {
                    "thought": "Recover.",
                    "action": "task_complete",
                    "action_input": {"message": "recovered"},
                }
            ),
        ]
    )
    agent = ReactAgent(
        client,
        [
            Tool("explode", "Fail", lambda arguments: (_ for _ in ()).throw(RuntimeError("boom"))),
            Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
        ],
        enable_planning=True,
        enable_compression=False,
        enable_adaptive_replanning=True,
        max_replans=2,
    )

    result = agent.run("recover from failure")

    assert result["final_answer"] == "recovered"
    assert result["metadata"]["adaptive_replanning_enabled"] is True
    assert result["metadata"]["replan_count"] == 1
    assert result["metadata"]["replan_decision_count"] == 1
    assert result["metadata"]["replan_signals"][0]["signal"]["kind"] == "tool_error"
    assert result["metadata"]["replan_strategy"] == "simplify_plan_skip_failed_tool"


def test_react_agent_adaptive_replan_respects_budget():
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "explode", "reason": "trigger failure"},
                        {"step": 2, "action": "task_complete", "reason": "finish"},
                    ]
                }
            ),
            json.dumps({"thought": "Try once.", "action": "explode", "action_input": {}}),
            json.dumps({"plan": [{"step": 1, "action": "explode", "reason": "retry once"}]}),
            json.dumps({"thought": "Try twice.", "action": "explode", "action_input": {}}),
            json.dumps(
                {
                    "thought": "Stop retrying.",
                    "action": "task_complete",
                    "action_input": {"message": "done after budget"},
                }
            ),
        ]
    )
    agent = ReactAgent(
        client,
        [
            Tool("explode", "Fail", lambda arguments: (_ for _ in ()).throw(RuntimeError("boom"))),
            Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
        ],
        enable_planning=True,
        enable_compression=False,
        enable_adaptive_replanning=True,
        max_replans=1,
    )

    result = agent.run("recover with one replan")

    assert result["final_answer"] == "done after budget"
    assert result["metadata"]["replan_count"] == 1
    assert result["metadata"]["replan_decision_count"] == 2
    assert result["metadata"]["replan_skipped_count"] == 1
    assert result["metadata"]["replan_maxed_count"] == 1


def test_react_agent_adaptive_replan_handles_parse_error():
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "task_complete", "reason": "finish"},
                    ]
                }
            ),
            "not json",
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "task_complete", "reason": "repair format"},
                    ]
                }
            ),
            json.dumps(
                {
                    "thought": "Use strict JSON.",
                    "action": "task_complete",
                    "action_input": {"message": "format repaired"},
                }
            ),
        ]
    )
    agent = ReactAgent(
        client,
        [Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done"))],
        enable_planning=True,
        enable_compression=False,
        enable_adaptive_replanning=True,
        max_replans=1,
    )

    result = agent.run("finish after parse repair")

    assert result["final_answer"] == "format repaired"
    assert result["metadata"]["parse_error_count"] == 1
    assert result["metadata"]["replan_signals"][0]["signal"]["kind"] == "parse_error"
    assert result["metadata"]["replan_strategy"] == "repair_response_format"


def test_react_agent_adaptive_replan_records_repeated_failures(tmp_path):
    trace_path = tmp_path / "repeat.jsonl"
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "explode", "reason": "trigger failure"},
                        {"step": 2, "action": "task_complete", "reason": "finish"},
                    ]
                }
            ),
            json.dumps({"thought": "Try once.", "action": "explode", "action_input": {}}),
            json.dumps({"plan": [{"step": 1, "action": "explode", "reason": "retry"}]}),
            json.dumps({"thought": "Try twice.", "action": "explode", "action_input": {}}),
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "task_complete", "reason": "recover"},
                    ]
                }
            ),
            json.dumps(
                {
                    "thought": "Recover.",
                    "action": "task_complete",
                    "action_input": {"message": "done"},
                }
            ),
        ]
    )
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        client,
        [
            Tool("explode", "Fail", lambda arguments: (_ for _ in ()).throw(RuntimeError("boom"))),
            Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
        ],
        enable_planning=True,
        enable_compression=False,
        enable_adaptive_replanning=True,
        max_replans=2,
        trace_writer=writer,
    )

    result = agent.run("recover from a repeated failure")
    writer.close()

    assert result["final_answer"] == "done"
    assert result["metadata"]["replan_count"] == 2
    assert result["metadata"]["repeated_failure_count"] == 1
    assert result["metadata"]["repeated_failures"][0]["action"] == "explode"
    assert result["metadata"]["repeated_failures"][0]["kind"] == "tool_error"

    decisions = [
        event["payload"]
        for event in load_trace_events(trace_path)
        if event["event"] == "replan_decision"
    ]
    assert [decision["repeated_failure"] for decision in decisions] == [False, True]
    assert decisions[1]["repeated_failure_details"]["action"] == "explode"


def test_react_agent_repeated_failure_policy_experiment_changes_only_repeated_decision(tmp_path):
    trace_path = tmp_path / "repeat-experiment.jsonl"
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "explode", "reason": "trigger failure"},
                        {"step": 2, "action": "task_complete", "reason": "finish"},
                    ]
                }
            ),
            json.dumps({"thought": "Try once.", "action": "explode", "action_input": {}}),
            json.dumps({"plan": [{"step": 1, "action": "explode", "reason": "retry"}]}),
            json.dumps({"thought": "Try twice.", "action": "explode", "action_input": {}}),
            json.dumps(
                {
                    "plan": [
                        {"step": 1, "action": "task_complete", "reason": "break loop"},
                    ]
                }
            ),
            json.dumps(
                {
                    "thought": "Recover.",
                    "action": "task_complete",
                    "action_input": {"message": "done"},
                }
            ),
        ]
    )
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        client,
        [
            Tool("explode", "Fail", lambda arguments: (_ for _ in ()).throw(RuntimeError("boom"))),
            Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
        ],
        enable_planning=True,
        enable_compression=False,
        enable_adaptive_replanning=True,
        enable_repeated_failure_policy_experiment=True,
        max_replans=2,
        trace_writer=writer,
    )

    result = agent.run("recover from a repeated failure with experiment")
    writer.close()

    assert result["final_answer"] == "done"
    assert result["metadata"]["repeated_failure_policy_experiment_enabled"] is True
    assert result["metadata"]["repeated_failure_policy_applied_count"] == 1
    assert result["metadata"]["replan_strategy_counts"]["break_repeated_failure_loop"] == 1

    decisions = [
        event["payload"]
        for event in load_trace_events(trace_path)
        if event["event"] == "replan_decision"
    ]
    assert decisions[0]["strategy"] == "simplify_plan_skip_failed_tool"
    assert decisions[1]["strategy"] == "break_repeated_failure_loop"
