import json

from dm_agent.core.agent import ReactAgent
from dm_agent.core.critic import CriticAgent
from dm_agent.core.response_parser import json_candidates
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


def test_critic_agent_parses_structured_review():
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "passed": False,
                    "score": 0.25,
                    "reasons": ["missing edge-case handling"],
                    "suggested_fixes": ["check empty input before returning"],
                    "summary": "The completion is incomplete.",
                }
            )
        ]
    )
    critic = CriticAgent(client)

    review = critic.review(
        task="fix the regression",
        final_answer="done",
        metadata={"status": "running"},
        steps=[{"thought": "check", "action": "finish", "observation": "done"}],
    )

    assert review.passed is False
    assert review.score == 0.25
    assert review.reasons == ["missing edge-case handling"]
    assert review.suggested_fixes == ["check empty input before returning"]
    prompt = client.requests[0][0][1]["content"]
    assert "passed" in prompt
    assert "score" in prompt


def test_critic_empty_json_fence_uses_shared_candidate_semantics():
    raw = "```json\n\n```"
    client = FakeRespondClient([raw])

    review = CriticAgent(client).review(task="reject empty review", final_answer="done")

    assert "" in json_candidates(raw)
    assert review.passed is False
    assert review.score == 0.0


def test_react_agent_critic_blocks_bad_completion_and_accepts_retry(tmp_path):
    trace_path = tmp_path / "critic.jsonl"
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "thought": "I think this is done.",
                    "action": "finish",
                    "action_input": {"answer": "bad"},
                }
            ),
            json.dumps(
                {
                    "passed": False,
                    "score": 0.2,
                    "reasons": ["missing edge-case handling"],
                    "suggested_fixes": ["revisit the final assertion"],
                    "summary": "The first attempt is incomplete.",
                }
            ),
            json.dumps(
                {
                    "thought": "I will fix the edge case.",
                    "action": "finish",
                    "action_input": {"answer": "good"},
                }
            ),
            json.dumps(
                {
                    "passed": True,
                    "score": 0.95,
                    "reasons": [],
                    "suggested_fixes": [],
                    "summary": "Looks correct.",
                }
            ),
        ]
    )
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        client,
        [Tool("task_complete", "Finish", lambda arguments: "finished")],
        enable_planning=False,
        enable_compression=False,
        critic=CriticAgent(client),
        trace_writer=writer,
    )

    result = agent.run("finish after review")
    writer.close()

    assert result["final_answer"] == "good"
    assert result["metadata"]["critic_review_count"] == 2
    assert result["metadata"]["critic_fail_count"] == 1
    assert result["metadata"]["critic_pass_count"] == 1
    assert result["steps"][0]["observation"].startswith("Critic rejected completion.")
    event_names = [event["event"] for event in load_trace_events(trace_path)]
    assert "critic_review" in event_names


def test_critic_blocks_task_complete_tool_and_accepts_retry():
    def review(passed: bool, summary: str) -> str:
        return json.dumps(
            {
                "passed": passed,
                "score": 0.95 if passed else 0.2,
                "reasons": [] if passed else ["the tool output is not a real completion"],
                "suggested_fixes": [] if passed else ["do the actual work first"],
                "summary": summary,
            }
        )

    def act(message: str) -> str:
        return json.dumps(
            {
                "thought": "I believe the task is done.",
                "action": "task_complete",
                "action_input": {"message": message},
            }
        )

    client = FakeRespondClient(
        [
            act("bad"),
            review(False, "The first attempt is incomplete."),
            act("good"),
            review(True, "Looks correct."),
        ]
    )
    agent = ReactAgent(
        client,
        [Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done"))],
        enable_planning=False,
        enable_compression=False,
        critic=CriticAgent(client),
    )

    result = agent.run("finish through the task_complete tool")

    assert result["final_answer"] == "good"
    assert result["metadata"]["status"] == "success"
    assert result["metadata"]["critic_fail_count"] == 1
    assert result["metadata"]["critic_pass_count"] == 1
    assert result["steps"][0]["observation"].startswith("Critic rejected completion.")
