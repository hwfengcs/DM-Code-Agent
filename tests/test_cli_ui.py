from types import SimpleNamespace

from dm_agent import Tool
from dm_agent.cli import (
    Config,
    create_agent,
    create_step_callback,
    display_completion_screen,
    display_result,
    format_agent_context_status,
    parse_args,
    print_menu,
    resolve_advanced_features,
    validate_feature_args,
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


def test_display_result_uses_panel_style(capsys):
    display_result(
        {
            "final_answer": "done",
            "metadata": {"completion_summary": "任务已完成。结果：done"},
            "steps": [
                {
                    "thought": "inspect",
                    "action": "read_file",
                    "action_input": {"path": "app.py"},
                    "observation": "opened app.py",
                }
            ],
        },
        show_steps=True,
    )

    output = capsys.readouterr().out

    assert "执行步骤" in output
    assert "最终答案" in output
    assert "本轮总结" in output
    assert "任务已完成" in output
    assert "read_file" in output
    assert "done" in output


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


def test_cli_advanced_features_default_off(monkeypatch):
    monkeypatch.setattr("dm_agent.cli.args.load_config_from_file", lambda: {})

    args = parse_args(["do maintenance"])

    assert args.enable_adaptive_replanning is False
    assert args.max_replans == -1
    assert args.enable_repeated_failure_policy_experiment is False
    assert args.enable_evolution is False
    assert validate_feature_args(args) == ""


def test_cli_advanced_features_wire_into_agent(monkeypatch):
    monkeypatch.setattr("dm_agent.cli.args.load_config_from_file", lambda: {})
    args = parse_args(
        [
            "do maintenance",
            "--enable-evolution",
        ]
    )
    assert validate_feature_args(args) == ""

    config = Config(
        api_key="test-key",
        enable_evolution=args.enable_evolution,
    )

    advanced = resolve_advanced_features(config)
    assert advanced["adaptive_replanning"] is True
    assert advanced["repeated_failure_policy_experiment"] is True

    agent = create_agent(
        config,
        FakeClient(),
        [Tool("noop", "No operation.", lambda arguments: "ok")],
    )

    assert agent.enable_adaptive_replanning is True
    assert agent.enable_repeated_failure_policy_experiment is True


def test_cli_advanced_feature_validation(monkeypatch):
    monkeypatch.setattr("dm_agent.cli.args.load_config_from_file", lambda: {})

    bad_replans = parse_args(["task", "--enable-repeated-failure-policy-experiment"])
    assert "--enable-adaptive-replanning" in validate_feature_args(bad_replans)

    evolution_preset = parse_args(
        ["task", "--enable-repeated-failure-policy-experiment", "--enable-evolution"]
    )
    assert validate_feature_args(evolution_preset) == ""
