import json
from pathlib import Path

from dm_agent.benchmarks.swebench_lite.models import (
    SWEBenchInstance,
    SWEBenchResult,
    SWEBenchRunConfig,
    SWEBenchVerification,
)
from dm_agent.core.agent import ReactAgent
from dm_agent.core.reflexion import EpisodicMemory, Reflector
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


def test_episodic_memory_renders_bounded_lessons():
    memory = EpisodicMemory(max_lessons=2)
    memory.add("first lesson")
    memory.add("second lesson")
    memory.add("third lesson")

    prompt = memory.render_for_prompt()

    assert "first lesson" not in prompt
    assert "second lesson" in prompt
    assert "third lesson" in prompt
    assert len(memory) == 2


def test_reflector_generates_normalized_lesson():
    client = FakeRespondClient(["  Inspect the failing assertion before editing again.  \n"])
    reflector = Reflector(client)

    lesson = reflector.reflect(
        task="Fix the bug",
        final_answer="Reached step limit",
        metadata={"status": "max_steps_exceeded", "failure_reason": "Max steps exceeded"},
        steps=[{"thought": "try", "action": "echo", "observation": "ok"}],
    )

    assert lesson == "Inspect the failing assertion before editing again."
    assert "previous trial failed" in client.requests[0][0][1]["content"].lower()


def test_react_agent_reflexion_retries_with_lesson():
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "thought": "I will inspect once.",
                    "action": "echo",
                    "action_input": {"text": "still not done"},
                }
            ),
            "Run the smallest finishing step next time.",
            json.dumps(
                {
                    "thought": "Use the lesson and finish.",
                    "action": "finish",
                    "action_input": {"answer": "done after reflection"},
                }
            ),
        ]
    )
    agent = ReactAgent(
        client,
        [
            Tool("echo", "Echo text", lambda arguments: f"echo:{arguments['text']}"),
            Tool("task_complete", "Finish", lambda arguments: "finished"),
        ],
        max_steps=1,
        enable_planning=False,
        enable_compression=False,
        enable_reflexion=True,
        max_trials=2,
    )

    result = agent.run("finish, but only after learning")

    assert result["final_answer"] == "done after reflection"
    assert result["metadata"]["trial_count"] == 2
    assert result["metadata"]["trials"][0]["status"] == "max_steps_exceeded"
    assert result["metadata"]["trials"][1]["status"] == "success"
    assert len(agent.reflexion_memory) == 1
    second_trial_messages = client.requests[2][0]
    assert "Run the smallest finishing step next time." in second_trial_messages[0]["content"]


def _instance() -> SWEBenchInstance:
    return SWEBenchInstance(
        instance_id="octo__example-1",
        repo="octo/example",
        version="1.0",
        base_commit="0" * 40,
        environment_setup_commit="0" * 40,
        problem_statement="Fix the greeter.",
        fail_to_pass=["tests/test_app.py::test_bug"],
        pass_to_pass=["tests/test_app.py::test_existing"],
    )


def _swe_result(instance: SWEBenchInstance, *, trial: int, success: bool) -> SWEBenchResult:
    verification = SWEBenchVerification(
        patch_applied=True,
        fail_to_pass_pass=1 if success else 0,
        fail_to_pass_total=1,
        pass_to_pass_pass=1,
        pass_to_pass_total=1,
    )
    return SWEBenchResult(
        instance_id=instance.instance_id,
        repo=instance.repo,
        success=success,
        failure_reason="" if success else "fail_to_pass_unresolved",
        final_answer="fixed" if success else "not yet",
        actions=["edit_file"],
        steps_count=trial,
        tool_calls=trial,
        duration_seconds=float(trial),
        prompt_chars=100 * trial,
        completion_chars=10 * trial,
        estimated_tokens=30 * trial,
        request_count=trial,
        metadata={"status": "success", "trial": trial},
        verification=verification,
        prediction="diff --git a/app.py b/app.py\n" if success else "diff --git a/bad b/bad\n",
        workspace_path="",
        trial=trial,
    )


def test_swebench_runner_reflexion_retries_after_hidden_failure(
    monkeypatch,
    tmp_path: Path,
):
    from dm_agent.benchmarks.swebench_lite import runner as runner_module

    instance = _instance()
    calls = []

    def fake_run_single_trial(instance_arg, config, **kwargs):
        calls.append((kwargs["trial_number"], len(kwargs["reflexion_memory"])))
        return _swe_result(instance_arg, trial=kwargs["trial_number"], success=len(calls) == 2)

    class FakeReflector:
        def reflect(self, **kwargs):
            assert "fail_to_pass_unresolved" in kwargs["failure_feedback"]
            return "Read the failing behavior before editing again."

    monkeypatch.setattr(runner_module, "_run_single_trial", fake_run_single_trial)
    monkeypatch.setattr(runner_module, "_build_reflector", lambda config: (FakeReflector(), None))

    result = runner_module._run_single_instance(
        instance,
        SWEBenchRunConfig(
            workspace_root=str(tmp_path),
            enable_reflexion=True,
            max_trials=2,
        ),
        workspace_root=tmp_path,
        trace_dir=None,
    )

    assert calls == [(1, 0), (2, 1)]
    assert result.success is True
    assert result.metadata["trial_count"] == 2
    assert result.metadata["reflexion_lessons"] == [
        "Read the failing behavior before editing again."
    ]
    assert result.request_count == 3
