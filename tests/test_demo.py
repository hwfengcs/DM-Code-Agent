"""离线演示使用真实文件和 unittest 子进程，不调用模型或加载用户配置。"""

import json
from pathlib import Path

import pytest

from dm_agent.demo import FIXED_SOURCE, ORIGINAL_SOURCE, main, run_demo
from dm_agent.tracing import analyze_events, load_session_entries


def test_demo_runs_real_tests_and_keeps_original_evidence(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("The offline demo must not load configuration or make HTTP requests")

    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    monkeypatch.setattr("dotenv.load_dotenv", forbidden)
    monkeypatch.setattr("dm_agent.clients.llm_factory.create_llm_client", forbidden)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "user-secret-must-not-appear")
    output = tmp_path / "demo"
    original_cwd = Path.cwd()

    manifest = run_demo(output)

    assert Path.cwd() == original_cwd
    assert manifest["model_requests"] == 0
    assert manifest == json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert (output / "before" / "retry.py").read_text(encoding="utf-8") == ORIGINAL_SOURCE
    assert [(case["test_returncodes"], case["verification_gap"]) for case in manifest["cases"]] == [
        ([1, 0], False),
        ([], True),
    ]
    for case in manifest["cases"]:
        assert (output / case["workspace"] / "retry.py").read_text(encoding="utf-8") == FIXED_SOURCE
        assert (output / case["patch"]).read_text(encoding="utf-8").startswith("--- a/retry.py\n")
        trace = output / case["trace"]
        contents = trace.read_text(encoding="utf-8")
        assert "user-secret-must-not-appear" not in contents
        entries = load_session_entries(trace)
        start = next(entry["payload"] for entry in entries if entry["event"] == "run_start")
        assert start["metadata"]["demo"] is True
        assert start["metadata"]["source"] == "scripted"
        assert analyze_events(entries)["verification"]["gap"] == case["verification_gap"]
        assert not any(entry["event"] == "checkpoint" for entry in entries)
    verified = load_session_entries(output / "sessions" / "verified.jsonl")
    checks = [
        entry["payload"]
        for entry in verified
        if entry["event"] == "tool_call" and entry["payload"]["action"] == "run_tests"
    ]
    assert "FAILED (failures=1)" in checks[0]["observation"]
    assert "Ran 4 tests" in checks[0]["observation"]
    assert "Ran 4 tests" in checks[1]["observation"]
    assert "\nOK" in checks[1]["observation"]


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_demo_rejects_existing_content_without_changing_it(tmp_path, kind):
    output = tmp_path / "existing"
    if kind == "file":
        output.write_text("keep me", encoding="utf-8")
        sentinel = output
    else:
        output.mkdir()
        sentinel = output / "sentinel.txt"
        sentinel.write_text("keep me", encoding="utf-8")

    with pytest.raises(ValueError, match="existing files are preserved"):
        run_demo(output)

    assert sentinel.read_text(encoding="utf-8") == "keep me"


def test_demo_rejects_output_symlink(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    output = tmp_path / "linked"
    try:
        output.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("This environment does not permit symbolic links")

    with pytest.raises(ValueError, match="symbolic link"):
        run_demo(output)

    assert list(target.iterdir()) == []


def test_demo_cli_creates_evidence_without_pytest(tmp_path, monkeypatch, capsys):
    import dm_agent.tools.execution_tools as execution

    original_run = execution.subprocess.run
    commands = []

    def checked_run(command, **kwargs):
        commands.append(command)
        assert "pytest" not in command
        return original_run(command, **kwargs)

    monkeypatch.setattr(execution.subprocess, "run", checked_run)
    output = tmp_path / "empty"
    output.mkdir()

    assert main(["--output", str(output)]) == 0

    assert len(commands) == 2
    assert all("unittest" in command for command in commands)
    assert "No model is called" in capsys.readouterr().out
    assert main(["--output", str(output)]) == 2
    assert "existing files are preserved" in capsys.readouterr().err
