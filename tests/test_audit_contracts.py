"""Offline regressions for the contracts resolved after the November audits."""

import json
from types import SimpleNamespace

import pytest

from dm_agent.benchmarks.economics import summarize_report
from dm_agent.benchmarks.runner import run_benchmark_suite
from dm_agent.benchmarks.score_diff import compare_reports
from dm_agent.cli.args import parse_args, validate_feature_args
from dm_agent.cli.config import load_config_from_file
from dm_agent.core import ReactAgent
from dm_agent.core.events import BeforeToolCallEvent, EventBus
from dm_agent.evals.cli import main as eval_main
from dm_agent.evals.gate import evaluate_gate
from dm_agent.evals.real_runner import UsageTrackingClient, run_real_suite
from dm_agent.evals.runner import run_suite
from dm_agent.mcp.client import MCPClient
from dm_agent.mcp.manager import MCPManager
from dm_agent.memory.context_compressor import ContextCompressor, Mem0StyleMemory
from dm_agent.server.process import RunSpec, build_argv
from dm_agent.server.runs import _count_run_ends
from dm_agent.skills.base import ConfigSkill
from dm_agent.skills.manager import SkillManager
from dm_agent.skills.selector import SkillSelector
from dm_agent.tools import default_tools
from dm_agent.tools.code_index_tools import build_code_index, dependency_graph
from dm_agent.tracing.analysis import analyze_events
from dm_agent.tracing.summary import summarize_events
from swebench_verified.run import _load_resume_records


@pytest.mark.parametrize("run", [run_suite, run_real_suite, run_benchmark_suite])
@pytest.mark.parametrize("selection", [[], ["does-not-exist"], ["direct_finish", "missing"]])
def test_invalid_selections_fail_before_a_model_call(run, selection):
    with pytest.raises(ValueError):
        run(task_ids=selection)


def test_unknown_eval_cli_is_an_error_without_a_report(tmp_path):
    output = tmp_path / "report.json"
    assert eval_main(["--task", "missing", "--output", str(output)]) == 2
    assert not output.exists()


def test_mixed_usage_keeps_reported_and_estimated_tokens():
    responses = iter([{"usage": {"total_tokens": 10}}, {}])
    wrapped = UsageTrackingClient(
        SimpleNamespace(
            model="fake",
            base_url="",
            timeout=1,
            complete=lambda *a, **k: next(responses),
            extract_text=lambda data: "",
        )
    )
    wrapped.respond([{"role": "user", "content": "x" * 100}])
    wrapped.respond([{"role": "user", "content": "x" * 1000}])
    assert wrapped.usage.estimated_tokens == 260
    assert wrapped.usage.total_tokens == 10
    assert wrapped.usage.estimated_fallback_tokens == 250


def _report(success=True):
    return {
        "results": [{"task_id": "a", "variant": "full", "success": success}],
        "summary": {"overall_success_rate": 1.0, "variants": {"full": {"success_rate": 1.0}}},
    }


@pytest.mark.parametrize("value", ["false", 0, None])
def test_report_readers_reject_non_boolean_outcomes(value):
    report = _report(value)
    with pytest.raises(ValueError, match="boolean"):
        compare_reports(report, _report())
    with pytest.raises(ValueError, match="boolean"):
        summarize_report(report)
    assert evaluate_gate(report, min_success_rate=0, min_variant_rate=0)


def test_gate_rejects_a_fabricated_green_summary():
    assert evaluate_gate(_report(False), min_success_rate=0, min_variant_rate=0)


def test_repeat_counts_must_match():
    left, right = _report(), _report()
    right["results"] *= 2
    assert not compare_reports(left, right).comparable


def test_web_options_override_opposite_disk_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "enable_edit_guard": False,
                "enable_adaptive_replanning": True,
                "max_steps": 99,
            }
        )
    )
    argv = build_argv(
        RunSpec(
            "task",
            "deepseek",
            options={
                "enable_edit_guard": True,
                "enable_adaptive_replanning": False,
            },
        ),
        trace_path=tmp_path / "trace.jsonl",
    )
    args = parse_args(argv[3:])
    assert args.enable_edit_guard is True
    assert args.enable_adaptive_replanning is False
    assert args.max_steps != 99
    explicit = parse_args(["task", "--enable-edit-guard", "--disable-adaptive-replanning"])
    assert explicit.enable_edit_guard and not explicit.enable_adaptive_replanning


@pytest.mark.parametrize(
    "config", [{"provider": 1}, {"enable_edit_guard": "false"}, {"max_steps": True}]
)
def test_invalid_config_types_fall_back_without_crashing(tmp_path, monkeypatch, config):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(json.dumps(config))
    assert load_config_from_file() == {}


def test_ignored_cli_persistence_options_are_rejected():
    assert validate_feature_args(parse_args(["--trace", "x.jsonl"]))
    assert validate_feature_args(
        parse_args(["--conversation-stdin", "--trace", "x.jsonl", "--report", "x.html"])
    )


@pytest.mark.parametrize("steps", [0, -1, True])
def test_library_rejects_invalid_step_budget(steps):
    with pytest.raises(ValueError, match="max_steps"):
        ReactAgent(object(), default_tools(include_mcp=False), max_steps=steps)


def test_failed_hook_rolls_back_nested_arguments():
    bus = EventBus()

    def broken(event):
        event.arguments["nested"]["values"].append(2)
        raise RuntimeError("bad hook")

    bus.on("before_tool_call", broken)
    event = BeforeToolCallEvent("test", {"nested": {"values": [1]}}, 1, "run")
    bus.emit_before_tool_call(event)
    assert event.arguments == {"nested": {"values": [1]}}


def test_reading_error_class_does_not_create_failure_memory():
    memory = Mem0StyleMemory()
    extracted = memory._extract_from_message(
        {
            "role": "user",
            "content": "执行工具 read_file，输入：{}\n观察：class ExpectedError(Exception): pass",
        }
    )
    assert not any(item["text"].startswith("Observed failure:") for item in extracted)


def test_compression_uses_actual_window_and_only_absorbs_new_messages(monkeypatch):
    compressor = ContextCompressor(compress_every=1000, keep_recent=1, token_budget=1000)
    history = [{"role": "user", "content": "x" * 800} for _ in range(10)]
    assert compressor.should_compress(history)
    first = compressor.plan_compaction(history)
    compressor.accept_beneficial_compaction(first)
    assert not compressor.should_compress(history)
    captured = []
    monkeypatch.setattr(
        compressor.memory, "add_messages", lambda messages, **kw: captured.extend(messages)
    )
    compressor.plan_compaction([*history, {"role": "user", "content": "new"}])
    assert captured == [history[8]]


@pytest.mark.parametrize("config", [{"keywords": [1]}, {"patterns": "abc"}, {"priority": True}])
def test_invalid_skill_metadata_is_rejected(config):
    with pytest.raises(ValueError):
        ConfigSkill({"name": "test", **config})


def test_keyword_boundaries():
    assert SkillSelector._keyword_match("format text", ["orm"]) == 0
    assert SkillSelector._keyword_match("use orm models", ["orm"]) == 1
    assert SkillSelector._keyword_match("请检查数据库", ["数据库"]) == 1


def test_lost_mcp_reply_is_not_replayed(monkeypatch):
    manager = MCPManager()
    effects = []
    client = SimpleNamespace(is_running=lambda: True, last_error="lost reply")

    def call(*args):
        effects.append("written")
        client.is_running = lambda: False
        return None

    client.call_tool = call
    manager.clients["srv"] = client
    monkeypatch.setattr(
        manager, "_try_reconnect", lambda name: pytest.fail("replayed unknown outcome")
    )
    tool = manager._create_tool_wrapper(
        server_name="srv", tool_name="write", description="", input_schema={}
    )
    assert "执行结果未知" in tool.execute({})
    assert effects == ["written"]


def test_mcp_discovers_all_pages_and_rejects_cursor_cycles(monkeypatch):
    client = MCPClient("test", "unused", [])
    monkeypatch.setattr(client, "_send_notification", lambda method: True)
    replies = iter(
        [
            {"ok": True},
            {"tools": [{"name": "one"}], "nextCursor": "next"},
            {"tools": [{"name": "two"}]},
        ]
    )
    monkeypatch.setattr(client, "_send_message", lambda *args: next(replies))
    assert client._initialize()
    assert [item["name"] for item in client.tools] == ["one", "two"]
    replies = iter(
        [{"ok": True}, {"tools": [], "nextCursor": "next"}, {"tools": [], "nextCursor": "next"}]
    )
    assert not client._initialize()


def test_turn_count_ignores_internal_run_retries(tmp_path):
    path = tmp_path / "turns.jsonl"
    events = ["conversation_start", "turn_start", "run_end", "run_end"]
    path.write_text("".join(json.dumps({"event": event}) + "\n" for event in events))
    assert _count_run_ends(path) == 0
    with path.open("a") as handle:
        handle.write('{"event":"turn_end"}\n')
    assert _count_run_ends(path) == 1


def test_summary_and_analysis_stay_inside_the_selected_run():
    entries = [
        {"event": "run_start", "payload": {"task": "old"}},
        {"event": "run_end", "payload": {"status": "success", "final_answer": "old answer"}},
        {"event": "run_start", "payload": {"task": "new"}},
    ]
    assert summarize_events(entries)["task"] == "new"
    assert summarize_events(entries)["final_answer"] == ""
    assert summarize_events(entries, run_index=0)["final_answer"] == "old answer"
    assert analyze_events(entries)["task"] == "new"
    assert analyze_events(entries, run_index=0)["task"] == "old"


def test_index_reports_coverage_and_isolates_bad_encoding(tmp_path):
    (tmp_path / "a.py").write_bytes(b"\xff")
    (tmp_path / "b.py").write_text("def useful(): pass")
    assert json.loads(build_code_index({"root": str(tmp_path), "max_files": 1}))["truncated"]
    for tool in (build_code_index, dependency_graph):
        result = json.loads(tool({"root": str(tmp_path)}))
        assert result["parse_errors"][0]["path"] == "a.py"


def test_null_prediction_has_a_clear_error_and_is_preserved(tmp_path):
    path = tmp_path / "predictions.jsonl"
    path.write_bytes(b"null\n")
    with pytest.raises(ValueError, match="object"):
        _load_resume_records(path, {"a"})
    assert path.read_bytes() == b"null\n"


def test_user_skills_load_without_writing_the_installation(tmp_path, monkeypatch):
    monkeypatch.setattr("dm_agent.skills.manager.user_data_dir", lambda: tmp_path)
    directory = tmp_path / "skills"
    directory.mkdir()
    (directory / "good.json").write_text('{"name":"personal","keywords":["review"]}')
    (directory / "bad.json").write_text('{"name":"bad","keywords":[1]}')
    manager = SkillManager()
    manager.load_custom_skills()
    assert "personal" in manager.skills and "bad" not in manager.skills


def test_session_pages_reuse_parse_and_refresh_after_append(tmp_path, monkeypatch):
    from dm_agent.server.routes import sessions

    path = tmp_path / "trace.jsonl"
    path.write_text('{"event":"run_start","payload":{}}\n')
    original = sessions.load_session_entries
    calls = []

    def load(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(sessions, "load_session_entries", load)
    assert len(sessions._cached_entries(path)) == 1
    assert len(sessions._cached_entries(path)) == 1
    assert len(calls) == 1
    with path.open("a") as handle:
        handle.write('{"event":"run_end","payload":{}}\n')
    assert len(sessions._cached_entries(path)) == 2
    assert len(calls) == 2
