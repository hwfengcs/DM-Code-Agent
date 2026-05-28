from main import display_result, format_agent_context_status, print_menu


class FakeAgent:
    def get_context_stats(self):
        return {
            "conversation_messages": 4,
            "memory_items": 3,
            "compression_enabled": True,
        }


def test_cli_menu_uses_ascii_terminal_frame(capsys):
    print_menu()

    output = capsys.readouterr().out

    assert "-- 主菜单" in output
    assert "执行新任务" in output
    assert "╭" not in output
    assert "╰" not in output
    assert "─" not in output


def test_display_result_uses_panel_style(capsys):
    display_result(
        {
            "final_answer": "done",
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

    assert "-- 执行步骤" in output
    assert "-- 最终答案" in output
    assert "read_file" in output
    assert "done" in output


def test_agent_context_status_makes_memory_visible():
    assert format_agent_context_status(FakeAgent()) == (
        "history=4 messages | memory=3 items | compression=on"
    )
