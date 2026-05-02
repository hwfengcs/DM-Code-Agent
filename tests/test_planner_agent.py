import json

import pytest

from dm_agent.core.agent import ReactAgent
from dm_agent.core.planner import TaskPlanner
from dm_agent.tools.base import Tool


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
