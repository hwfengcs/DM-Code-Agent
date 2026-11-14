from types import SimpleNamespace

import pytest

from dm_agent import Tool
from dm_agent.cli.args import parse_args, validate_feature_args
from dm_agent.cli.config import Config, resolve_advanced_features
from dm_agent.cli.runner import create_agent, format_agent_context_status
from dm_agent.cli.ui import (
    create_step_callback,
    display_completion_screen,
    print_menu,
)


class FakeAgent:
    def get_context_stats(self):
        return {
            "conversation_messages": 4,
            "memory_items": 3,
            "compression_enabled": True,
        }


class FakeClient:
    def respond(self, messages, **extra):
        raise AssertionError("FakeClient should not be called during construction")


def test_cli_menu_renders_modern_command_palette(capsys):
    print_menu()

    output = capsys.readouterr().out

    assert "主菜单" in output
    assert "1" in output
    assert "6" in output
    assert "执行新任务" in output
    assert "多轮对话模式" in output
    assert "[1]" not in output


def test_agent_context_status_makes_memory_visible():
    assert format_agent_context_status(FakeAgent()) == (
        "history=4 messages | memory=3 items | compression=on"
    )


def test_completion_screen_surfaces_summary_and_review_hint(capsys):
    display_completion_screen(
        {
            "final_answer": "full answer",
            "metadata": {
                "status": "success",
                "duration_seconds": 3.2,
                "completion_summary": "complete summary",
                "tool_error_count": 0,
                "replan_count": 0,
                "memory_items": 2,
            },
            "steps": [{"action": "read_file", "observation": "opened"}],
        },
        task="do thing",
        context_status="history=4 messages | memory=3 items | compression=on",
        review_hint=True,
    )

    output = capsys.readouterr().out

    assert "complete summary" in output
    assert "full answer" in output
    assert "do thing" in output
    assert "history=4 messages" in output
    assert "v" in output
    assert "s" in output


def test_compact_step_callback_is_low_noise(capsys):
    callback = create_step_callback(False)

    for step_number in range(1, 12):
        callback(
            step_number,
            SimpleNamespace(
                action="read_file",
                action_input={"path": f"file_{step_number}.py"},
                thought="",
                observation="ok",
            ),
        )
    callback(
        12,
        SimpleNamespace(
            action="finish",
            action_input="done",
            thought="",
            observation="<finished>",
        ),
    )

    output = capsys.readouterr().out

    assert "01" in output
    assert "10" in output
    assert "finish" in output
    assert "02" not in output
    assert "09" not in output


@pytest.mark.parametrize(
    ("action", "observation", "expected"),
    [
        ("read_file", "文件 missing.py 不存在。", "err"),
        ("run_tests", "returncode: 2", "err"),
        ("read_file", "1: failed = True", "ok"),
        ("run_tests", "expected failure\nreturncode: 0", "ok"),
    ],
)
def test_cli_step_status_uses_tool_result_semantics(monkeypatch, action, observation, expected):
    from io import StringIO

    from rich.console import Console

    from dm_agent.cli import ui

    output = StringIO()
    monkeypatch.setattr(ui, "RICH_CONSOLE", Console(file=output, color_system=None, width=140))
    monkeypatch.setattr(ui.UI, "rich_enabled", staticmethod(lambda: True))
    monkeypatch.setattr(ui.UI, "clear", staticmethod(lambda: None))
    step = SimpleNamespace(action=action, action_input={}, thought="", observation=observation)

    create_step_callback(False)(10, step)
    assert expected.upper() in output.getvalue()

    output.seek(0)
    output.truncate()
    ui.display_step_page({"steps": [vars(step)]}, page=0, page_size=12)
    assert expected.upper() in output.getvalue()


def test_cli_advanced_features_default_off(monkeypatch):
    monkeypatch.setattr("dm_agent.cli.args.load_config_from_file", lambda: {})

    args = parse_args(["do maintenance"])

    assert args.enable_adaptive_replanning is False
    assert args.max_replans == -1
    assert validate_feature_args(args) == ""


def test_cli_advanced_features_wire_into_agent(monkeypatch):
    monkeypatch.setattr("dm_agent.cli.args.load_config_from_file", lambda: {})
    args = parse_args(["do maintenance", "--enable-adaptive-replanning", "--max-replans", "2"])
    assert validate_feature_args(args) == ""

    config = Config(
        api_key="test-key",
        enable_adaptive_replanning=args.enable_adaptive_replanning,
        max_replans=args.max_replans,
    )

    advanced = resolve_advanced_features(config)
    assert advanced["adaptive_replanning"] is True

    agent = create_agent(
        config,
        FakeClient(),
        [Tool("noop", "No operation.", lambda arguments: "ok")],
    )

    assert agent.enable_adaptive_replanning is True
    assert agent.max_replans == 2


def test_cli_advanced_feature_validation(monkeypatch):
    monkeypatch.setattr("dm_agent.cli.args.load_config_from_file", lambda: {})

    bad_replans = parse_args(["task", "--max-replans", "-2"])
    assert "--max-replans" in validate_feature_args(bad_replans)

    bad_observation = parse_args(["task", "--max-observation-chars", "10"])
    assert "--max-observation-chars" in validate_feature_args(bad_observation)

    bad_retries = parse_args(["task", "--llm-max-retries", "-1"])
    assert "--llm-max-retries" in validate_feature_args(bad_retries)

    ok = parse_args(["task", "--enable-adaptive-replanning"])
    assert validate_feature_args(ok) == ""


@pytest.mark.parametrize("max_steps", ["0", "-1"])
def test_cli_rejects_non_positive_step_budget(monkeypatch, max_steps):
    monkeypatch.setattr("dm_agent.cli.args.load_config_from_file", lambda: {})

    args = parse_args(["task", "--max-steps", max_steps])

    assert "--max-steps" in validate_feature_args(args)


def test_cli_rejects_trace_checkpoint_path_aliases(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dm_agent.cli.args.load_config_from_file", lambda: {})
    args = parse_args(
        ["task", "--trace", "same.jsonl", "--checkpoint", str(tmp_path / "same.jsonl")]
    )

    assert "不能指向同一个文件" in validate_feature_args(args)


def test_cli_rejects_trace_checkpoint_hardlinks(tmp_path, monkeypatch):
    monkeypatch.setattr("dm_agent.cli.args.load_config_from_file", lambda: {})
    trace = tmp_path / "trace.jsonl"
    trace.touch()
    checkpoint = tmp_path / "checkpoint.jsonl"
    checkpoint.hardlink_to(trace)
    args = parse_args(["task", "--trace", str(trace), "--checkpoint", str(checkpoint)])

    assert "不能指向同一个文件" in validate_feature_args(args)


@pytest.mark.parametrize(
    ("extra_args", "expected_model", "expected_url"),
    [
        ([], "gpt-5", ""),
        (["--model", "deepseek-chat"], "deepseek-chat", ""),
        (["--base-url", "http://localhost:8000/v1"], "gpt-5", "http://localhost:8000/v1"),
    ],
)
def test_cli_provider_override_uses_its_own_defaults(
    monkeypatch, extra_args, expected_model, expected_url
):
    from dm_agent.cli import main

    monkeypatch.setattr(
        "dm_agent.cli.args.load_config_from_file",
        lambda: {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
        },
    )
    captured = []

    def run_task(config, task, **kwargs):
        captured.append(config)
        return 0

    monkeypatch.setattr("dm_agent.cli.run_single_task", run_task)

    assert (
        main(["task", "--provider", "openai", "--api-key", "test", "--no-extensions", *extra_args])
        == 0
    )
    assert captured[0].model == expected_model
    assert captured[0].base_url == expected_url
