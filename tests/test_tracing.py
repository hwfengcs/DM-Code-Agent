import json
import os
from contextlib import contextmanager
from pathlib import Path

from main import Config, write_run_report

from dm_agent.core.agent import ReactAgent
from dm_agent.tools import default_tools
from dm_agent.tracing import TraceWriter, load_trace_events
from dm_agent.tracing.cli import main as trace_main
from dm_agent.tracing.cli import replay_tools, summarize_events


class FakeRespondClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def respond(self, messages, **extra):
        if not self.responses:
            raise AssertionError("FakeRespondClient ran out of responses")
        return self.responses.pop(0)


@contextmanager
def chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def test_trace_writer_records_agent_run_and_view_cli(tmp_path):
    trace_path = tmp_path / "run.jsonl"
    (tmp_path / "input.txt").write_text("agent trace ready\n", encoding="utf-8")
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "thought": "Read the file.",
                    "action": "read_file",
                    "action_input": {"path": "input.txt"},
                }
            ),
            json.dumps(
                {
                    "thought": "Finish.",
                    "action": "finish",
                    "action_input": {"answer": "trace complete"},
                }
            ),
        ]
    )
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        client,
        default_tools(include_mcp=False),
        enable_planning=False,
        enable_compression=False,
        trace_writer=writer,
    )

    with chdir(tmp_path):
        result = agent.run("read input.txt")
    writer.close()

    assert result["final_answer"] == "trace complete"
    events = load_trace_events(trace_path)
    event_names = [event["event"] for event in events]
    assert "run_start" in event_names
    assert "llm_call" in event_names
    assert "tool_call" in event_names
    assert "run_end" in event_names

    summary = summarize_events(events)
    assert summary["status"] == "success"
    assert summary["step_count"] == 2
    assert summary["steps"][0]["action"] == "read_file"
    assert trace_main(["view", str(trace_path), "--json"]) == 0
    assert trace_main(["replay", str(trace_path)]) == 0


def test_trace_tool_replay_can_reexecute_safe_file_read(tmp_path):
    trace_path = tmp_path / "run.jsonl"
    (tmp_path / "input.txt").write_text("same observation\n", encoding="utf-8")
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        FakeRespondClient(
            [
                json.dumps(
                    {
                        "thought": "Read.",
                        "action": "read_file",
                        "action_input": {"path": "input.txt"},
                    }
                ),
                json.dumps({"thought": "Done.", "action": "finish", "action_input": "ok"}),
            ]
        ),
        default_tools(include_mcp=False),
        enable_planning=False,
        enable_compression=False,
        trace_writer=writer,
    )

    with chdir(tmp_path):
        agent.run("read input")
    writer.close()

    tool_results = replay_tools(load_trace_events(trace_path), tmp_path)

    assert tool_results
    assert tool_results[0]["action"] == "read_file"
    assert tool_results[0]["matches"] is True


def test_run_report_writes_human_readable_markdown(tmp_path):
    report_path = tmp_path / "report.md"
    result = {
        "final_answer": "done",
        "steps": [
            {
                "action": "read_file",
                "observation": "content",
            }
        ],
        "metadata": {
            "status": "success",
            "duration_seconds": 0.5,
            "tool_error_count": 0,
            "replan_count": 0,
        },
    }

    write_run_report(
        report_path,
        config=Config(api_key="test-key", provider="deepseek", model="deepseek-chat"),
        task="read a file",
        result=result,
        trace_path=tmp_path / "trace.jsonl",
        git_status_before=[" M existing.py"],
        git_status_after=[" M existing.py", "?? new_file.py"],
    )

    text = report_path.read_text(encoding="utf-8")
    assert "DM-Code-Agent Run Report" in text
    assert "read a file" in text
    assert "`read_file`" in text
    assert "trace.jsonl" in text
    assert "Dirty entries before run: `1`" in text
    assert "?? new_file.py" in text
