"""Characterization tests for the public trace CLI contract.

These fixtures deliberately use fixed ids, timestamps, and payloads.  The tests pin the
current command output before ``dm_agent.tracing.cli`` is split into smaller modules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dm_agent.tracing as tracing
from dm_agent.tracing import cli as trace_cli


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )


def _json_output(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def _linked_events(
    run_id: str,
    id_prefix: str,
    day: int,
    events: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    linked: list[dict[str, Any]] = []
    parent_id = ""
    for index, (event, payload) in enumerate(events, start=1):
        entry_id = f"{id_prefix}-{index:04d}"
        linked.append(
            {
                "id": entry_id,
                "parent_id": parent_id,
                "timestamp": f"2026-01-{day:02d}T00:00:{index - 1:02d}+00:00",
                "run_id": run_id,
                "event": event,
                "payload": payload,
            }
        )
        parent_id = entry_id
    return linked


def _gap_events() -> list[dict[str, Any]]:
    return _linked_events(
        "trace-fixed",
        "trace-fi",
        1,
        [
            ("run_start", {"schema_version": "2.0", "task": "repair widget"}),
            (
                "runtime",
                {
                    "provider": "test-provider",
                    "model": "test-model",
                    "base_url": "https://api.example.invalid",
                },
            ),
            ("plan", {"steps": [{"action": "read_file"}, {"action": "finish"}]}),
            (
                "step",
                {
                    "step_number": 1,
                    "action": "read_file",
                    "observation": "widget.py contents",
                },
            ),
            (
                "tool_call",
                {
                    "step_number": 1,
                    "action": "read_file",
                    "action_input": {"path": "widget.py"},
                    "observation": "widget.py contents",
                    "failed": False,
                },
            ),
            ("step", {"step_number": 2, "action": "finish", "observation": "<finished>"}),
            (
                "run_end",
                {
                    "status": "success",
                    "final_answer": "fixed",
                    "duration_seconds": 1.25,
                    "metadata": {},
                },
            ),
        ],
    )


def _verified_events() -> list[dict[str, Any]]:
    return _linked_events(
        "verified-fixed",
        "verify-f",
        2,
        [
            ("run_start", {"schema_version": "2.0", "task": "verify widget"}),
            (
                "runtime",
                {
                    "provider": "test-provider",
                    "model": "test-model",
                    "base_url": "https://api.example.invalid",
                },
            ),
            ("plan", {"steps": [{"action": "run_tests"}, {"action": "finish"}]}),
            ("step", {"step_number": 1, "action": "run_tests", "observation": "2 passed"}),
            (
                "tool_call",
                {
                    "step_number": 1,
                    "action": "run_tests",
                    "action_input": {},
                    "observation": "2 passed",
                    "failed": False,
                },
            ),
            ("step", {"step_number": 2, "action": "finish", "observation": "<finished>"}),
            (
                "run_end",
                {
                    "status": "success",
                    "final_answer": "verified",
                    "duration_seconds": 0.5,
                    "metadata": {},
                },
            ),
        ],
    )


def _blocked_replay_events() -> list[dict[str, Any]]:
    return _linked_events(
        "blocked-fixed",
        "blocked",
        3,
        [
            ("run_start", {"schema_version": "2.0", "task": "blocked replay"}),
            (
                "step",
                {"step_number": 1, "action": "run_shell", "observation": "should not run"},
            ),
            (
                "tool_call",
                {
                    "step_number": 1,
                    "action": "run_shell",
                    "action_input": {"command": "echo blocked"},
                    "observation": "should not run",
                    "failed": False,
                },
            ),
            (
                "run_end",
                {
                    "status": "success",
                    "final_answer": "not replayed",
                    "duration_seconds": 0.1,
                    "metadata": {},
                },
            ),
        ],
    )


def _summary_for_gap_trace() -> dict[str, Any]:
    return {
        "run_id": "trace-fixed",
        "schema_version": "2.0",
        "task": "repair widget",
        "status": "success",
        "final_answer": "fixed",
        "duration_seconds": 1.25,
        "provider": "test-provider",
        "model": "test-model",
        "base_url": "https://api.example.invalid",
        "event_count": 7,
        "step_count": 2,
        "tool_call_count": 1,
        "replan_count": 0,
        "plan_steps": [{"action": "read_file"}, {"action": "finish"}],
        "steps": [
            {
                "step_number": 1,
                "action": "read_file",
                "observation": "widget.py contents",
            },
            {"step_number": 2, "action": "finish", "observation": "<finished>"},
        ],
    }


def _analysis_for_trace(*, verified: bool) -> dict[str, Any]:
    return {
        "run_id": "verified-fixed" if verified else "trace-fixed",
        "task": "verify widget" if verified else "repair widget",
        "status": "success",
        "primary_failure_stage": "none",
        "final_failure_stage": "none",
        "signals": [] if verified else ["verification_gap"],
        "recovery": {
            "failure_event_count": 0,
            "first_failure_step": None,
            "first_failure_event": None,
            "replan_count": 0,
            "replanned_after_failure": False,
            "recovered": False,
        },
        "verification": {
            "actions": ([{"step_number": 1, "action": "run_tests"}] if verified else []),
            "count": 1 if verified else 0,
            "finish_step": 2,
            "before_finish": verified,
            "gap": not verified,
        },
        "hallucination_signals": {
            "edit_without_read_count": 0,
            "edit_guard_blocks": 0,
            "truncation_hits": 0,
            "truncation_hit_rate": 0.0,
            "missing_path_reference_count": 0,
        },
        "metadata_counters": {},
        "trace_health": {
            "score": 1.0 if verified else 0.8,
            "grade": "good" if verified else "warning",
            "issues": [] if verified else ["verification_gap"],
        },
    }


def test_trace_package_and_cli_keep_the_current_import_surface() -> None:
    required_package_exports = {
        "SessionWriter",
        "TraceWriter",
        "analyze_events",
        "analyze_trace_directory",
        "conversation_from_entries",
        "diff_events",
        "find_entry",
        "find_entry_index",
        "fork_session",
        "latest_checkpoint_entry",
        "load_session_entries",
        "load_trace_events",
        "message_entries",
        "new_entry_id",
        "normalize_entries",
        "rebuild_context",
        "render_trace_directory_markdown",
        "summarize_events",
    }
    assert required_package_exports <= set(tracing.__all__)
    for name in required_package_exports:
        assert getattr(tracing, name) is not None

    for name in (
        "analyze_events",
        "analyze_trace_directory",
        "diff_events",
        "fork_session",
        "render_trace_directory_markdown",
        "summarize_events",
    ):
        assert getattr(trace_cli, name) is getattr(tracing, name)
    assert callable(trace_cli.main)
    assert callable(trace_cli.parse_args)
    assert callable(trace_cli.replay_tools)


def test_view_cli_human_json_and_raw_outputs_are_exact(tmp_path: Path, capsys) -> None:
    events = _gap_events()
    trace_path = tmp_path / "gap.jsonl"
    _write_jsonl(trace_path, events)

    assert trace_cli.main(["view", str(trace_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "Trace run: trace-fixed\n"
        "Task: repair widget\n"
        "Status: success\n"
        "Provider: test-provider\n"
        "Model: test-model\n"
        "Events: 7\n"
        "Steps: 2\n"
        "\n"
        "1. read_file -> widget.py contents\n"
        "2. finish -> <finished>\n"
        "\n"
        "Final: fixed\n"
    )
    assert captured.err == ""

    assert trace_cli.main(["view", str(trace_path), "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.out == _json_output(_summary_for_gap_trace())
    assert captured.err == ""

    assert trace_cli.main(["view", str(trace_path), "--json", "--raw"]) == 0
    captured = capsys.readouterr()
    assert captured.out == _json_output(events)
    assert captured.err == ""


def test_replay_cli_dry_blocked_and_json_outputs_are_exact(tmp_path: Path, capsys) -> None:
    trace_path = tmp_path / "gap.jsonl"
    _write_jsonl(trace_path, _gap_events())

    assert trace_cli.main(["replay", str(trace_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ("Replay mode: dry\n" "Task: repair widget\n" "Steps replayed: 2\n")
    assert captured.err == ""

    expected_dry = {
        "run_id": "trace-fixed",
        "task": "repair widget",
        "mode": "dry",
        "status": "ok",
        "events_replayed": 7,
        "steps_replayed": 2,
        "tool_replay": [],
        "mismatch_count": 0,
    }
    assert trace_cli.main(["replay", str(trace_path), "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.out == _json_output(expected_dry)
    assert captured.err == ""

    blocked_path = tmp_path / "blocked.jsonl"
    _write_jsonl(blocked_path, _blocked_replay_events())
    assert trace_cli.main(["replay", str(blocked_path), "--execute-tools"]) == 1
    captured = capsys.readouterr()
    assert captured.out == (
        "Replay mode: tool\n"
        "Task: blocked replay\n"
        "Steps replayed: 1\n"
        "Tool calls replayed: 1\n"
        "Mismatches: 1\n"
        "- BLOCKED run_shell step=1\n"
    )
    assert captured.err == ""

    expected_blocked = {
        "run_id": "blocked-fixed",
        "task": "blocked replay",
        "mode": "tool",
        "status": "blocked",
        "events_replayed": 4,
        "steps_replayed": 1,
        "tool_replay": [
            {
                "step_number": 1,
                "action": "run_shell",
                "status": "blocked",
                "matches": False,
                "expected_observation": "should not run",
                "actual_observation": "Execution tools require --allow-shell.",
            }
        ],
        "mismatch_count": 1,
    }
    assert trace_cli.main(["replay", str(blocked_path), "--execute-tools", "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == _json_output(expected_blocked)
    assert captured.err == ""


def test_analyze_cli_human_and_json_outputs_are_exact(tmp_path: Path, capsys) -> None:
    trace_path = tmp_path / "gap.jsonl"
    _write_jsonl(trace_path, _gap_events())

    assert trace_cli.main(["analyze", str(trace_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "Trace analysis\n"
        "Task: repair widget\n"
        "Status: success\n"
        "Primary failure stage: none\n"
        "Final failure stage: none\n"
        "Recovery: failures=0, replans=0, replanned_after_failure=false, recovered=false\n"
        "Verification: actions=0, before_finish=false, gap=true\n"
        "Hallucination signals: edit_without_read=0, guard_blocks=0, truncations=0, "
        "missing_paths=0\n"
        "Health: warning (0.80)\n"
        "Issues:\n"
        "- verification_gap\n"
    )
    assert captured.err == ""

    assert trace_cli.main(["analyze", str(trace_path), "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.out == _json_output(_analysis_for_trace(verified=False))
    assert captured.err == ""


def test_analyze_dir_cli_human_json_and_markdown_outputs_are_exact(tmp_path: Path, capsys) -> None:
    gap_path = tmp_path / "a-gap.jsonl"
    verified_path = tmp_path / "b-verified.jsonl"
    _write_jsonl(gap_path, _gap_events())
    _write_jsonl(verified_path, _verified_events())

    expected_report = {
        "mode": "trace_directory_analysis",
        "directory": str(tmp_path),
        "pattern": "*.jsonl",
        "summary": {
            "total_files": 2,
            "analyzed_traces": 2,
            "error_count": 0,
            "verification_gap_count": 1,
            "runs_with_failures": 0,
            "recovered_runs": 0,
            "recovery_success_rate": None,
            "hallucination_signals": {
                "edit_without_read_count": 0,
                "edit_guard_blocks": 0,
                "truncation_hits": 0,
                "missing_path_reference_count": 0,
            },
            "trace_health_counts": {"good": 1, "warning": 1},
            "primary_failure_stage_counts": {"none": 2},
            "final_failure_stage_counts": {"none": 2},
        },
        "analyses": [
            {"path": str(gap_path), "analysis": _analysis_for_trace(verified=False)},
            {"path": str(verified_path), "analysis": _analysis_for_trace(verified=True)},
        ],
        "errors": [],
    }
    expected_human = (
        "Trace directory analysis\n"
        f"Directory: {tmp_path}\n"
        "Pattern: *.jsonl\n"
        "Traces: 2/2 analyzed\n"
        "Errors: 0\n"
        "Verification gaps: 1\n"
        "Hallucination signals: edit_without_read=0, guard_blocks=0, truncations=0, "
        "missing_paths=0\n"
        "Trace health:\n"
        "- good: 1\n"
        "- warning: 1\n"
        "Final failure stages:\n"
        "- none: 2\n"
    )

    assert trace_cli.main(["analyze-dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == expected_human
    assert captured.err == ""

    assert trace_cli.main(["analyze-dir", str(tmp_path), "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.out == _json_output(expected_report)
    assert captured.err == ""

    markdown_path = tmp_path / "reports" / "trace-analysis.md"
    assert trace_cli.main(["analyze-dir", str(tmp_path), "--markdown", str(markdown_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == expected_human + f"Markdown report: {markdown_path}\n"
    assert captured.err == ""
    assert markdown_path.read_text(encoding="utf-8") == (
        "# Trace Directory Analysis\n"
        "\n"
        "This report is generated from trace metadata only. It omits raw prompts, observations, "
        "tool outputs, and final answers.\n"
        "\n"
        f"- Directory: `{tmp_path}`\n"
        "- Pattern: `*.jsonl`\n"
        "- Traces analyzed: `2/2`\n"
        "- Errors: `0`\n"
        "- Verification gaps: `1`\n"
        "\n"
        "## Trace Health\n"
        "\n"
        "- `good`: `1`\n"
        "- `warning`: `1`\n"
        "\n"
        "## Recovery & Hallucination Signals\n"
        "\n"
        "- Recovery success rate: `n/a` (no runs with failures)\n"
        "- Edits without a prior read: `0`\n"
        "- Edit-guard blocks: `0`\n"
        "- Truncated observations: `0`\n"
        "- Missing-path references: `0`\n"
        "\n"
        "## Final Failure Stages\n"
        "\n"
        "- `none`: `2`\n"
        "\n"
        "## Trace Details\n"
        "\n"
        "| Trace | Status | Health | Final failure | Verification gap | Replans |\n"
        "| --- | --- | --- | --- | ---: | ---: |\n"
        "| `a-gap.jsonl` | `success` | `warning` | `none` | yes | 0 |\n"
        "| `b-verified.jsonl` | `success` | `good` | `none` | no | 0 |\n"
    )


def test_diff_cli_human_and_json_outputs_are_exact(tmp_path: Path, capsys) -> None:
    base_path = tmp_path / "base.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    _write_jsonl(base_path, _gap_events())
    _write_jsonl(candidate_path, _verified_events())

    expected_diff = {
        "base": {
            "run_id": "trace-fixed",
            "task": "repair widget",
            "status": "success",
            "provider": "test-provider",
            "model": "test-model",
            "step_count": 2,
            "tool_call_count": 1,
            "replan_count": 0,
            "duration_seconds": 1.25,
        },
        "candidate": {
            "run_id": "verified-fixed",
            "task": "verify widget",
            "status": "success",
            "provider": "test-provider",
            "model": "test-model",
            "step_count": 2,
            "tool_call_count": 1,
            "replan_count": 0,
            "duration_seconds": 0.5,
        },
        "status_changed": False,
        "task_changed": True,
        "final_answer_changed": True,
        "plan_changed": True,
        "metrics": {
            "step_count": {"base": 2, "candidate": 2, "delta": 0},
            "tool_call_count": {"base": 1, "candidate": 1, "delta": 0},
            "replan_count": {"base": 0, "candidate": 0, "delta": 0},
            "duration_seconds": {"base": 1.25, "candidate": 0.5, "delta": -0.75},
        },
        "action_sequence": {
            "base": ["read_file", "finish"],
            "candidate": ["run_tests", "finish"],
            "common_prefix": 0,
            "changes": [{"step_number": 1, "base": "read_file", "candidate": "run_tests"}],
        },
        "tool_usage": {
            "base": {"finish": 1, "read_file": 1},
            "candidate": {"finish": 1, "run_tests": 1},
            "delta": {
                "read_file": {"base": 1, "candidate": 0, "delta": -1},
                "run_tests": {"base": 0, "candidate": 1, "delta": 1},
            },
        },
        "plan": {
            "base": ["read_file", "finish"],
            "candidate": ["run_tests", "finish"],
        },
    }

    assert trace_cli.main(["diff", str(base_path), str(candidate_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "Trace diff\n"
        "Base: repair widget\n"
        "Candidate: verify widget\n"
        "Status: success -> success\n"
        "Steps: 2 -> 2 (+0)\n"
        "Tool calls: 1 -> 1 (+0)\n"
        "Replans: 0 -> 0 (+0)\n"
        "\n"
        "Action common prefix: 0\n"
        "Action changes:\n"
        "- Step 1: read_file -> run_tests\n"
        "\n"
        "Tool usage delta:\n"
        "- read_file: 1 -> 0 (-1)\n"
        "- run_tests: 0 -> 1 (+1)\n"
        "\n"
        "Plan changed: yes\n"
        "Final answer changed: yes\n"
    )
    assert captured.err == ""

    assert trace_cli.main(["diff", str(base_path), str(candidate_path), "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.out == _json_output(expected_diff)
    assert captured.err == ""


def test_fork_cli_human_json_nonresumable_and_error_outputs_are_exact(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "session.jsonl"
    entries = _linked_events(
        "session-fixed",
        "session",
        4,
        [
            ("run_start", {"schema_version": "2.0", "task": "fork task"}),
            (
                "checkpoint",
                {
                    "step_number": 1,
                    "state": {
                        "task": "fork task",
                        "step_count": 1,
                        "conversation_history": [],
                        "steps": [],
                        "metadata": {},
                        "plan": [],
                    },
                },
            ),
            ("step", {"step_number": 2, "action": "finish", "observation": "<finished>"}),
        ],
    )
    _write_jsonl(source, entries)

    human_output = tmp_path / "branch-human.jsonl"
    assert (
        trace_cli.main(["fork", str(source), "--at", "session-0002", "--output", str(human_output)])
        == 0
    )
    captured = capsys.readouterr()
    assert captured.out == (
        f"Forked from: {source}\n"
        "At entry: session-0002\n"
        "Entries copied: 2\n"
        f"Output: {human_output}\n"
        "Resumable at step 1 (entry session-0002)\n"
        f"Next: dm-agent --resume {human_output}\n"
    )
    assert captured.err == ""

    json_output = tmp_path / "branch-json.jsonl"
    expected_json = {
        "mode": "session_fork",
        "source": str(source),
        "output": str(json_output),
        "forked_from_entry_id": "session-0002",
        "entry_count": 2,
        "resumable_checkpoint_entry_id": "session-0002",
        "resumable_step_number": 1,
    }
    assert (
        trace_cli.main(
            [
                "fork",
                str(source),
                "--at",
                "session-0002",
                "--output",
                str(json_output),
                "--json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.out == _json_output(expected_json)
    assert captured.err == ""

    legacy_source = tmp_path / "legacy.jsonl"
    legacy_entries = _linked_events(
        "legacy-fixed",
        "legacy-fixed",
        5,
        [
            ("run_start", {"task": "legacy fork"}),
            ("step", {"step_number": 1, "action": "finish", "observation": "done"}),
        ],
    )
    _write_jsonl(legacy_source, legacy_entries)
    legacy_output = tmp_path / "legacy-branch.jsonl"
    assert (
        trace_cli.main(
            [
                "fork",
                str(legacy_source),
                "--at",
                "legacy-fixed-0002",
                "--output",
                str(legacy_output),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.out == (
        f"Forked from: {legacy_source}\n"
        "At entry: legacy-fixed-0002\n"
        "Entries copied: 2\n"
        f"Output: {legacy_output}\n"
        "No checkpoint entry at or before the fork point: this branch can be inspected but not "
        "resumed. Re-run the source task with --checkpoint <file>.jsonl to make forks "
        "resumable.\n"
    )
    assert captured.err == ""

    assert trace_cli.main(["fork", str(source), "--at", "missing-entry"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Fork failed: No session entry matches id 'missing-entry'.\n"


def test_trace_cli_load_errors_are_exact(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing.jsonl"
    assert trace_cli.main(["view", str(missing)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"Trace not found: {missing}\n"

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text("{not-json}\n", encoding="utf-8")
    assert trace_cli.main(["analyze", str(invalid)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "Invalid trace JSONL: Expecting property name enclosed in double quotes: "
        "line 1 column 2 (char 1)\n"
    )
