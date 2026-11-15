import sys
import time

import pytest

from dm_agent.core.observation import is_failure_observation
from dm_agent.memory.context_budget import truncate_observation
from dm_agent.server.process import RunProcess
from dm_agent.tools.execution_tools import run_python, run_tests


def test_timeout_preserves_output_and_returns_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dm_agent.tools.execution.tempfile.gettempdir", lambda: str(tmp_path))
    start = time.monotonic()
    result = run_python({"code": "import time; print('before'); time.sleep(30)", "timeout": 0.2})
    assert time.monotonic() - start < 10
    assert "before" in result
    assert "timeout" in result
    assert is_failure_observation(result, action="run_python")
    assert any(b"before" in p.read_bytes() for p in tmp_path.rglob("*.stdout"))


def test_output_budget_stops_producer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dm_agent.tools.execution.tempfile.gettempdir", lambda: str(tmp_path))
    result = run_python({"code": "while True: print('x' * 8192)", "max_output_bytes": 16384})
    assert "output limit" in result
    assert len(result) < 100000
    assert is_failure_observation(result, action="run_python")


@pytest.mark.parametrize("value", [0, -1, float("nan"), True, "1"])
def test_invalid_timeout_is_rejected(value):
    with pytest.raises(ValueError, match="timeout"):
        run_python({"code": "pass", "timeout": value})


def test_small_observation_keeps_exit_status():
    result = truncate_observation("x" * 5000 + "\nreturncode: 2", max_chars=400, action="run_shell")
    assert is_failure_observation(result.text, action="run_shell")


def test_unittest_absolute_file(tmp_path):
    target = tmp_path / "test_external.py"
    target.write_text(
        "import unittest\nclass TestExternal(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n"
    )
    assert "returncode: 0" in run_tests({"test_path": str(target), "framework": "unittest"})


def test_unittest_package_file_preserves_relative_imports(tmp_path):
    package = tmp_path / "external_tests"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "helpers.py").write_text("EXPECTED = 42\n")
    target = package / "test_external.py"
    target.write_text(
        "import unittest\nfrom .helpers import EXPECTED\n"
        "class TestExternal(unittest.TestCase):\n"
        " def test_ok(self): self.assertEqual(EXPECTED, 42)\n"
    )
    result = run_tests({"test_path": str(target), "framework": "unittest"})
    assert "returncode: 0" in result


def test_stop_reaps_descendants_after_root_exits(tmp_path):
    marker = tmp_path / "late.txt"
    child = "import time; from pathlib import Path; time.sleep(1); Path('late.txt').write_text('orphan')"
    process = RunProcess(
        [
            sys.executable,
            "-c",
            f"import subprocess,sys; subprocess.Popen([sys.executable, '-c', {child!r}])",
        ],
        cwd=tmp_path,
        trace_path=tmp_path / "trace.jsonl",
    )
    process.start()
    try:
        assert process.wait(5) == 0
        process.stop(grace_seconds=0)
        time.sleep(1.2)
        assert not marker.exists()
    finally:
        process.stop(grace_seconds=0)
