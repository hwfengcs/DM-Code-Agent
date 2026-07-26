"""Tests for the tool circuit breaker (default off)."""

from __future__ import annotations

import json

import pytest

from dm_agent.core.agent import ReactAgent
from dm_agent.core.circuit_breaker import (
    STATE_CLOSED,
    STATE_OPEN,
    ToolCircuitBreaker,
)
from dm_agent.tools.base import Tool


class FakeRespondClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def respond(self, messages, **extra):
        if not self.responses:
            raise AssertionError("FakeRespondClient ran out of responses")
        return self.responses.pop(0)


def _action(action: str, action_input) -> str:
    return json.dumps(
        {"thought": "step", "action": action, "action_input": action_input},
        ensure_ascii=False,
    )


def test_state_machine_opens_after_threshold_and_recovers_via_probe():
    breaker = ToolCircuitBreaker(threshold=3, cooldown_steps=2)

    assert breaker.record("run_shell", "tool_error", failed=True, step=1) == STATE_CLOSED
    assert breaker.record("run_shell", "tool_error", failed=True, step=2) == STATE_CLOSED
    assert breaker.record("run_shell", "tool_error", failed=True, step=3) == STATE_OPEN

    # Open during cooldown: intercepted with a non-failure message.
    message = breaker.intercept("run_shell", 4)
    assert message is not None
    assert not ReactAgent._is_failure_observation(message)

    # After cooldown the probe is allowed (half-open).
    assert breaker.intercept("run_shell", 5) is None
    # Probe succeeds -> closed again, later calls allowed.
    assert breaker.record("run_shell", "", failed=False, step=5) == STATE_CLOSED
    assert breaker.intercept("run_shell", 6) is None


def test_state_machine_reopens_when_probe_fails():
    breaker = ToolCircuitBreaker(threshold=2, cooldown_steps=2)
    breaker.record("run_shell", "tool_error", failed=True, step=1)
    breaker.record("run_shell", "tool_error", failed=True, step=2)

    assert breaker.intercept("run_shell", 3) is not None
    assert breaker.intercept("run_shell", 4) is None  # probe allowed
    assert breaker.record("run_shell", "tool_error", failed=True, step=4) == STATE_OPEN
    assert breaker.intercept("run_shell", 5) is not None
    assert breaker.total_trips == 2


def test_success_resets_consecutive_failures():
    breaker = ToolCircuitBreaker(threshold=3, cooldown_steps=2)
    breaker.record("run_shell", "tool_error", failed=True, step=1)
    breaker.record("run_shell", "tool_error", failed=True, step=2)
    breaker.record("run_shell", "", failed=False, step=3)
    assert breaker.record("run_shell", "tool_error", failed=True, step=4) == STATE_CLOSED


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        ToolCircuitBreaker(threshold=1)
    with pytest.raises(ValueError):
        ToolCircuitBreaker(cooldown_steps=0)


def test_agent_blocks_fourth_call_after_three_identical_failures():
    calls = {"count": 0}

    def failing_runner(arguments):
        calls["count"] += 1
        raise RuntimeError("boom")

    tools = [
        Tool("explode", "Fail", failing_runner),
        Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
    ]
    client = FakeRespondClient(
        [
            _action("explode", {}),
            _action("explode", {}),
            _action("explode", {}),
            _action("explode", {}),  # should be intercepted, runner not called
            _action("finish", "switched approach after breaker"),
        ]
    )
    agent = ReactAgent(
        client,
        tools,
        enable_planning=False,
        enable_compression=False,
        enable_circuit_breaker=True,
        circuit_breaker_threshold=3,
        circuit_breaker_cooldown=5,
    )

    result = agent.run("keep failing", max_steps=8)

    assert result["metadata"]["status"] == "success"
    assert calls["count"] == 3
    assert result["metadata"]["circuit_breaker_block_count"] == 1
    assert result["metadata"]["circuit_breaker_trip_count"] == 1
    blocked_observation = result["steps"][3]["observation"]
    assert "temporarily disabled" in blocked_observation


def test_agent_default_off_keeps_calling_failing_tool():
    calls = {"count": 0}

    def failing_runner(arguments):
        calls["count"] += 1
        raise RuntimeError("boom")

    tools = [
        Tool("explode", "Fail", failing_runner),
        Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
    ]
    client = FakeRespondClient(
        [
            _action("explode", {}),
            _action("explode", {}),
            _action("explode", {}),
            _action("explode", {}),
            _action("finish", "gave up"),
        ]
    )
    agent = ReactAgent(
        client,
        tools,
        enable_planning=False,
        enable_compression=False,
    )

    result = agent.run("keep failing", max_steps=8)

    assert calls["count"] == 4
    assert result["metadata"]["circuit_breaker_enabled"] is False
    assert result["metadata"]["circuit_breaker_block_count"] == 0
