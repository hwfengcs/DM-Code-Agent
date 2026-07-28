"""Dry timeline replay and explicit tool re-execution."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dm_agent.tools import default_tools

from .summary import summarize_events

EXECUTION_TOOLS = {"run_python", "run_shell", "run_tests", "run_linter"}


def _replay(
    events: list[dict[str, Any]],
    *,
    execute_tools: bool,
    allow_shell: bool,
    workspace: Path | None,
    as_json: bool,
) -> int:
    summary = summarize_events(events)
    result: dict[str, Any] = {
        "run_id": summary.get("run_id"),
        "task": summary.get("task"),
        "mode": "tool" if execute_tools else "dry",
        "status": "ok",
        "events_replayed": len(events),
        "steps_replayed": summary.get("step_count", 0),
        "tool_replay": [],
        "mismatch_count": 0,
    }

    if execute_tools:
        replay_workspace = workspace or Path.cwd()
        tool_results = replay_tools(events, replay_workspace, allow_shell=allow_shell)
        result["tool_replay"] = tool_results
        result["mismatch_count"] = sum(1 for item in tool_results if not item["matches"])
        if any(item["status"] == "blocked" for item in tool_results):
            result["status"] = "blocked"
        elif result["mismatch_count"]:
            result["status"] = "mismatch"

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Replay mode: {result['mode']}")
        print(f"Task: {result.get('task', '')}")
        print(f"Steps replayed: {result['steps_replayed']}")
        if execute_tools:
            print(f"Tool calls replayed: {len(result['tool_replay'])}")
            print(f"Mismatches: {result['mismatch_count']}")
            for item in result["tool_replay"]:
                marker = "OK" if item["matches"] else item["status"].upper()
                print(f"- {marker} {item['action']} step={item['step_number']}")

    return 0 if result["status"] == "ok" else 1


def replay_tools(
    events: Iterable[dict[str, Any]],
    workspace: Path,
    *,
    allow_shell: bool = False,
) -> list[dict[str, Any]]:
    tools = {tool.name: tool for tool in default_tools(include_mcp=False)}
    results: list[dict[str, Any]] = []

    for event in events:
        if event.get("event") != "tool_call":
            continue
        payload = event.get("payload", {})
        action = payload.get("action", "")
        if action in {"finish", "error"}:
            continue

        item: dict[str, Any] = {
            "step_number": payload.get("step_number"),
            "action": action,
            "status": "ok",
            "matches": False,
            "expected_observation": payload.get("observation", ""),
            "actual_observation": "",
        }

        tool = tools.get(action)
        if tool is None:
            item["status"] = "unknown_tool"
            results.append(item)
            continue
        if action in EXECUTION_TOOLS and not allow_shell:
            item["status"] = "blocked"
            item["actual_observation"] = "Execution tools require --allow-shell."
            results.append(item)
            continue
        try:
            with chdir(workspace):
                actual = tool.execute(payload.get("action_input") or {})
        except Exception as exc:
            actual = f"Tool execution failed: {exc}"
            item["status"] = "error"

        item["actual_observation"] = actual
        item["matches"] = actual == item["expected_observation"]
        if item["status"] == "ok" and not item["matches"]:
            item["status"] = "mismatch"
        results.append(item)

    return results


@contextmanager
def chdir(path: Path):
    previous = Path.cwd()
    path.mkdir(parents=True, exist_ok=True)
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)
