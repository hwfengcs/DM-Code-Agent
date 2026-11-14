"""无需 API key 的演示：脚本化决策驱动真实文件工具和 unittest。"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, cast

from dm_agent.clients.base_client import BaseLLMClient
from dm_agent.core.agent import ReactAgent
from dm_agent.evals.scripted_client import ScriptedLLMClient
from dm_agent.tools.base import Tool
from dm_agent.tools.execution_tools import run_tests
from dm_agent.tools.file_tools import edit_file, read_file
from dm_agent.tracing import TraceWriter, analyze_events, load_session_entries

DEMO_DESCRIPTION = (
    "Scripted assistant decisions with real file edits and local unittest checks. "
    "No model is called. This demonstration is not a benchmark score."
)
ORIGINAL_SOURCE = '''def should_retry(attempt: int, max_attempts: int) -> bool:
    """Return whether another attempt fits within the configured limit."""
    return attempt <= max_attempts
'''
FIXED_SOURCE = ORIGINAL_SOURCE.replace("attempt <= max_attempts", "attempt < max_attempts")
TEST_SOURCE = """import unittest

from retry import should_retry


class RetryBoundaryTests(unittest.TestCase):
    def test_first_attempt_is_allowed(self):
        self.assertTrue(should_retry(0, 3))

    def test_last_available_attempt_is_allowed(self):
        self.assertTrue(should_retry(2, 3))

    def test_exhausted_budget_is_rejected(self):
        self.assertFalse(should_retry(3, 3))

    def test_over_budget_is_rejected(self):
        self.assertFalse(should_retry(4, 3))
"""
DEMO_TASK = "Fix the retry boundary in retry.py, then run the local tests to verify the change."


class _DemoTraceWriter(TraceWriter):
    """在既有记录协议中标注演示来源，不改变内核行为。"""

    def start_run(self, task: str, *, metadata: dict[str, Any] | None = None) -> None:
        super().start_run(
            task,
            metadata={**(metadata or {}), "demo": True, "source": "scripted"},
        )


def _action(thought: str, action: str, action_input: Any) -> str:
    return json.dumps({"thought": thought, "action": action, "action_input": action_input})


def _responses(*, verify: bool) -> list[str]:
    test = _action(
        "Run the four local unittest checks.",
        "run_tests",
        {"test_path": ".", "framework": "unittest"},
    )
    actions = [test] if verify else []
    actions.extend(
        [
            _action(
                "Inspect the retry condition before editing it.", "read_file", {"path": "retry.py"}
            ),
            _action(
                "Reject another attempt when the configured budget is exhausted.",
                "edit_file",
                {
                    "path": "retry.py",
                    "old_string": "attempt <= max_attempts",
                    "new_string": "attempt < max_attempts",
                },
            ),
        ]
    )
    if verify:
        actions.append(test)
    actions.append(
        _action(
            "Finish the scripted demonstration.",
            "finish",
            {
                "answer": (
                    "Fixed the retry boundary. All four unittest checks passed."
                    if verify
                    else "Updated the retry boundary. Claimed completion without running tests."
                )
            },
        )
    )
    return actions


def _write_new(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _run_case(output: Path, *, verify: bool) -> dict[str, Any]:
    name = "verified" if verify else "unverified"
    workspace = output / name
    workspace.mkdir()
    _write_new(workspace / "retry.py", ORIGINAL_SOURCE)
    _write_new(workspace / "test_retry.py", TEST_SOURCE)
    trace_path = output / "sessions" / f"{name}.jsonl"
    responses = _responses(verify=verify)
    tools = [
        Tool("read_file", "Read a UTF-8 file.", read_file),
        Tool("edit_file", "Replace unique text in a file.", edit_file),
        Tool("run_tests", "Run local unittest checks.", run_tests),
    ]
    previous = Path.cwd()
    try:
        os.chdir(workspace)
        with _DemoTraceWriter(trace_path) as writer:
            writer.record(
                "runtime",
                {
                    "provider": "scripted",
                    "model": "offline-demo",
                    "demo": True,
                    "source": "scripted",
                    "description": DEMO_DESCRIPTION,
                },
            )
            agent = ReactAgent(
                cast(BaseLLMClient, ScriptedLLMClient(responses, model="offline-demo")),
                tools,
                enable_planning=False,
                enable_compression=False,
                trace_writer=writer,
                max_steps=len(responses),
            )
            with redirect_stdout(StringIO()):
                result = agent.run(DEMO_TASK)
    finally:
        os.chdir(previous)

    after = (workspace / "retry.py").read_text(encoding="utf-8")
    patch_name = f"{name}.patch"
    _write_new(
        output / patch_name,
        "".join(
            difflib.unified_diff(
                ORIGINAL_SOURCE.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile="a/retry.py",
                tofile="b/retry.py",
            )
        ),
    )
    events = load_session_entries(trace_path)
    analysis = analyze_events(events)
    test_returncodes = [
        int(match.group(1))
        for step in result["steps"]
        if step["action"] == "run_tests"
        for match in re.finditer(r"(?m)^returncode: (-?\d+)$", step["observation"])
    ]
    expected_codes = [1, 0] if verify else []
    if (
        result["metadata"]["status"] != "success"
        or after != FIXED_SOURCE
        or test_returncodes != expected_codes
        or analysis["verification"]["gap"] != (not verify)
    ):
        raise RuntimeError(
            f"The {name} demo did not produce the expected evidence; inspect {trace_path}"
        )
    return {
        "id": name,
        "trace": f"sessions/{name}.jsonl",
        "workspace": name,
        "patch": patch_name,
        "status": result["metadata"]["status"],
        "step_count": len(result["steps"]),
        "test_returncodes": test_returncodes,
        "verification_gap": analysis["verification"]["gap"],
    }


def run_demo(output: Path) -> dict[str, Any]:
    """只在指定的新目录或空目录里运行两个公开 fixture，并返回可移植清单。

    该外围入口使用进程工作目录，适合 CLI 或串行构建脚本，不用于并发服务器请求。
    """
    if output.is_symlink():
        raise ValueError("The demo output must not be a symbolic link.")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(
            "The demo output must be a new or empty directory; existing files are preserved."
        )
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "sessions").mkdir()
    (output / "before").mkdir()
    _write_new(output / "before" / "retry.py", ORIGINAL_SOURCE)
    _write_new(output / "README.txt", DEMO_DESCRIPTION + "\n")
    manifest = {
        "schema_version": 1,
        "source": "scripted",
        "demo": True,
        "description": DEMO_DESCRIPTION,
        "model_requests": 0,
        "cases": [_run_case(output, verify=True), _run_case(output, verify=False)],
    }
    _write_new(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=DEMO_DESCRIPTION)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("demo-run"),
        help="New or empty output directory (default: demo-run).",
    )
    args = parser.parse_args(argv)
    print(DEMO_DESCRIPTION)
    try:
        manifest = run_demo(args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        return 2
    for case in manifest["cases"]:
        evidence = (
            "tests failed, then passed" if case["id"] == "verified" else "verification gap detected"
        )
        print(f"  {case['id']}: {case['step_count']} steps; {evidence}")
    output = args.output.resolve()
    print(f"Evidence saved in: {output}")
    print(f'dm-agent-trace analyze "{output / "sessions" / "verified.jsonl"}"')
    print(f'dm-agent-web --read-only --sessions-dir "{output / "sessions"}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
