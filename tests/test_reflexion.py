import json

from dm_agent.core.agent import ReactAgent
from dm_agent.core.reflexion import EpisodicMemory, Lesson, Reflector
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


def test_reflexion_memory_file_roundtrip(tmp_path):
    from dm_agent.cli import load_reflexion_memory_file, save_reflexion_memory_file

    path = tmp_path / "lessons.json"
    memory = EpisodicMemory()
    memory.add("Always run the tests before finishing.", metadata={"trial": 1})
    save_reflexion_memory_file(str(path), memory)

    loaded = load_reflexion_memory_file(str(path))
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded.lessons[0].text == "Always run the tests before finishing."
    assert isinstance(loaded.lessons[0], Lesson)

    missing = load_reflexion_memory_file(str(tmp_path / "missing.json"))
    assert isinstance(missing, EpisodicMemory)
    assert len(missing) == 0

    assert load_reflexion_memory_file("") is None
