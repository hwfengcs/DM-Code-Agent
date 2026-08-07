from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from swebench_verified.analyze import (
    AnalysisInputError,
    analyze_paths,
    main,
    render_json,
    render_markdown,
)

IDS = [
    "org__repo-1",
    "org__repo-2",
    "org__repo-3",
    "other__lib-4",
    "other__lib-5",
    "other__lib-6",
]


def _prediction(
    instance_id: str,
    *,
    patch: str | None = "diff --git a/a b/a\n",
    status: str = "success",
    difficulty: str = "<15 min fix",
    diagnostics: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "instance_id": instance_id,
        "model_name_or_path": "dm-agent-test",
        "model_patch": patch,
        "dm_status": status,
        "dm_failure": "",
        "dm_patch_chars": len(patch) if patch is not None else None,
        "dm_duration_seconds": 1.5,
        "dm_difficulty": difficulty,
    }
    if diagnostics:
        row.update(
            {
                "dm_diagnostics_version": 1,
                "dm_steps": 4,
                "dm_replans": 1,
                "dm_parse_errors": 0,
                "dm_parse_repairs": 0,
                "dm_parse_error_context_omitted_count": 0,
                "dm_parse_error_context_omitted_chars": 0,
                "dm_truncations": 0,
                "dm_edit_guard_blocks": 0,
                "dm_edit_noops": 0,
                "dm_repeat_search_blocks": 0,
                "dm_edit_state_revisits": 0,
                "dm_edit_cycle_blocks": 0,
            }
        )
    row.update(extra)
    return row


def _manifest(ids: list[str]) -> dict[str, Any]:
    repo_counts: dict[str, int] = {}
    for instance_id in ids:
        owner, repository_with_issue = instance_id.split("__", 1)
        repository = repository_with_issue.rpartition("-")[0]
        repo = f"{owner}/{repository}"
        repo_counts[repo] = repo_counts.get(repo, 0) + 1
    return {
        "schema_version": 1,
        "selected_count": len(ids),
        "instance_ids": ids,
        "repo_counts": repo_counts,
        "difficulty_counts": {"<15 min fix": len(ids)},
    }


def _report(
    ids: list[str],
    *,
    resolved: list[str],
    unresolved: list[str],
    empty: list[str],
    error: list[str],
    submitted_order: list[str] | None = None,
    incomplete_ids: list[str] | None = None,
) -> dict[str, Any]:
    completed = resolved + unresolved
    submitted = submitted_order or ids
    return {
        "schema_version": 2,
        "total_instances": 500,
        "submitted_instances": len(submitted),
        "completed_instances": len(completed),
        "resolved_instances": len(resolved),
        "unresolved_instances": len(unresolved),
        "empty_patch_instances": len(empty),
        "error_instances": len(error),
        "submitted_ids": submitted,
        "completed_ids": completed,
        "resolved_ids": resolved,
        "unresolved_ids": unresolved,
        "empty_patch_ids": empty,
        "error_ids": error,
        "incomplete_ids": incomplete_ids or [f"full-split-{index}" for index in range(494)],
    }


def _write_json(path: Path, value: Any) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _write_predictions(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _event(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"event": event, "payload": payload}


def _write_trace(
    path: Path,
    instance_id: str,
    *,
    status: str = "success",
    actions: list[tuple[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    runtime_id: str | None = None,
    malformed_line: bool = False,
) -> Path:
    actions = actions or [("read_file", {"path": "a.py"}), ("task_complete", {})]
    owner, repository_with_issue = (runtime_id or instance_id).split("__", 1)
    repository = repository_with_issue.rpartition("-")[0]
    events: list[dict[str, Any]] = [
        _event(
            "runtime",
            {"instance_id": runtime_id or instance_id, "repo": f"{owner}/{repository}"},
        ),
        _event("run_start", {"schema_version": "2.0"}),
    ]
    for index, (action, action_input) in enumerate(actions, start=1):
        events.append(
            _event(
                "step",
                {
                    "step_number": index,
                    "action": action,
                    "action_input": action_input,
                    "observation": "ok",
                },
            )
        )
        if action not in {"task_complete", "finish"}:
            events.append(
                _event(
                    "tool_call",
                    {
                        "step_number": index,
                        "action": action,
                        "action_input": action_input,
                        "failed": False,
                        "observation": "ok",
                    },
                )
            )
    events.append(
        _event(
            "run_end",
            {
                "status": status,
                "duration_seconds": 2.0,
                "metadata": metadata or {},
            },
        )
    )
    lines = [json.dumps(event, ensure_ascii=False, sort_keys=True) for event in events]
    if malformed_line:
        lines.insert(2, "{bad json")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run_event(run_id: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
    value = _event(event, payload)
    value["run_id"] = run_id
    return value


def _append_run(
    events: list[dict[str, Any]],
    instance_id: str,
    run_id: str,
    *,
    actions: list[tuple[str, Any]],
    status: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    events.append(_run_event(run_id, "runtime", {"instance_id": instance_id, "repo": "org/repo"}))
    events.append(_run_event(run_id, "run_start", {"schema_version": "2.0"}))
    for index, (action, action_input) in enumerate(actions, start=1):
        events.append(
            _run_event(
                run_id,
                "step",
                {"step_number": index, "action": action, "action_input": action_input},
            )
        )
        if action not in {"finish", "task_complete"}:
            events.append(
                _run_event(
                    run_id,
                    "tool_call",
                    {"step_number": index, "action": action, "action_input": action_input},
                )
            )
    if status is not None:
        events.append(
            _run_event(
                run_id,
                "run_end",
                {"status": status, "duration_seconds": 1.0, "metadata": metadata or {}},
            )
        )


def _write_detail(
    root: Path,
    instance_id: str,
    *,
    f2p_failures: int = 0,
    p2p_failures: int = 0,
    apply_failure: bool = False,
) -> Path:
    directory = root / instance_id
    directory.mkdir(parents=True)
    if apply_failure:
        detail = {"patch_successfully_applied": False, "resolved": False}
    else:
        detail = {
            "patch_successfully_applied": True,
            "resolved": f2p_failures == 0 and p2p_failures == 0,
            "tests_status": {
                axis: {"success": [], "failure": []}
                for axis in ("FAIL_TO_PASS", "PASS_TO_PASS", "FAIL_TO_FAIL", "PASS_TO_FAIL")
            },
        }
        detail["tests_status"]["FAIL_TO_PASS"]["failure"] = [
            f"hidden-f2p-{index}" for index in range(f2p_failures)
        ]
        detail["tests_status"]["PASS_TO_PASS"]["failure"] = [
            f"hidden-p2p-{index}" for index in range(p2p_failures)
        ]
    return _write_json(directory / "report.json", {instance_id: detail})


def _bundle(tmp_path: Path) -> dict[str, Any]:
    rows = [
        _prediction(IDS[0]),
        _prediction(IDS[1]),
        _prediction(
            IDS[2],
            status="max_steps_exceeded",
            patch="diff 3",
            dm_parse_errors=2,
            dm_edit_guard_blocks=1,
        ),
        _prediction(IDS[3]),
        _prediction(IDS[4], status="max_steps_exceeded", patch=""),
        _prediction(IDS[5], patch=None, status="agent_exception", diagnostics=False),
    ]
    predictions = _write_predictions(tmp_path / "predictions.jsonl", rows)
    manifest = _write_json(tmp_path / "manifest.json", _manifest(IDS))
    report = _write_json(
        tmp_path / "report.json",
        _report(
            IDS,
            resolved=[IDS[0]],
            unresolved=[IDS[1], IDS[2], IDS[3]],
            empty=[IDS[4]],
            error=[IDS[5]],
            submitted_order=[IDS[3], IDS[0], IDS[5], IDS[2], IDS[4], IDS[1]],
        ),
    )
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    _write_trace(
        trace_dir / f"{IDS[0]}.jsonl",
        IDS[0],
        actions=[("read_file", {"path": "a.py"}), ("run_tests", {})],
    )
    _write_trace(
        trace_dir / f"{IDS[2]}.jsonl",
        IDS[2],
        status="max_steps_exceeded",
        actions=[
            ("read_file", {"path": "a.py"}),
            ("edit_file", {"path": "a.py", "old_string": "x", "new_string": "y"}),
            ("run_python", {"code": "print(1)"}),
        ],
        metadata={"parse_error_count": 2, "edit_guard_block_count": 1},
        malformed_line=True,
    )
    _write_trace(
        trace_dir / f"{IDS[4]}.jsonl",
        IDS[4],
        status="max_steps_exceeded",
        actions=[("read_file", {"path": "a.py"})],
    )
    detail_dir = tmp_path / "details"
    _write_detail(detail_dir, IDS[0])
    _write_detail(detail_dir, IDS[1], f2p_failures=1)
    _write_detail(detail_dir, IDS[2], f2p_failures=1, p2p_failures=1)
    _write_detail(detail_dir, IDS[3], p2p_failures=1)
    _write_detail(detail_dir, IDS[5], apply_failure=True)
    return {
        "predictions": predictions,
        "manifest": manifest,
        "report": report,
        "trace_dir": trace_dir,
        "detail_dir": detail_dir,
    }


def test_minimal_bundle_separates_three_axes_and_ignores_incomplete_ids(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    analysis = analyze_paths(
        bundle["predictions"],
        bundle["report"],
        manifest_path=bundle["manifest"],
        trace_dirs=[bundle["trace_dir"]],
        harness_log_dir=bundle["detail_dir"],
    )

    all_summary = analysis["summary"]["all"]
    assert all_summary["denominator"] == 6
    assert all_summary["official_outcomes"] == {
        "resolved": 1,
        "unresolved": 3,
        "empty_patch": 1,
        "harness_error": 1,
        "incomplete": 0,
        "unknown": 0,
    }
    assert all_summary["harness_details"] == {
        "all_passed": 1,
        "f2p_only": 1,
        "f2p_and_p2p": 1,
        "p2p_only": 1,
        "patch_apply_failure": 1,
        "detail_unavailable": 1,
        "unmeasured": 0,
        "invalid": 0,
    }
    assert all_summary["agent_outcomes"] == {
        "success": 3,
        "max_steps": 2,
        "exception": 1,
        "unknown": 0,
    }
    assert all_summary["agent_metrics"]["steps"]["sum"] == 20
    assert all_summary["agent_metrics"]["steps"]["unmeasured_count"] == 1

    rows = {row["instance_id"]: row for row in analysis["instances"]}
    assert [row["instance_id"] for row in analysis["instances"]] == IDS
    assert rows[IDS[0]]["official"]["outcome"] == "resolved"
    assert rows[IDS[0]]["harness_detail"]["status"] == "all_passed"
    assert rows[IDS[2]]["agent"]["outcome"] == "max_steps"
    assert "parse_error" in rows[IDS[2]]["failure_labels"]
    assert "guard_block" in rows[IDS[2]]["failure_labels"]
    assert "f2p_unresolved" in rows[IDS[1]]["failure_labels"]
    assert "p2p_regression" in rows[IDS[3]]["failure_labels"]
    assert rows[IDS[4]]["failure_labels"][:3] == ["empty_patch", "no_edit", "max_steps"]
    assert rows[IDS[5]]["harness_detail"]["status"] == "patch_apply_failure"
    assert rows[IDS[5]]["patch"]["is_empty"] is None
    assert rows[IDS[5]]["agent"]["counters"]["parse_errors"] is None


def test_prefix_scopes_are_additive_and_report_order_is_set_based(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    analysis = analyze_paths(
        bundle["predictions"],
        bundle["report"],
        manifest_path=bundle["manifest"],
        prefix_count=3,
    )
    scopes = analysis["summary"]
    assert set(scopes) >= {"all", "prefix_1_3", "remainder_4_6"}
    for outcome in ("resolved", "unresolved", "empty_patch", "harness_error"):
        assert scopes["all"]["official_outcomes"].get(outcome, 0) == (
            scopes["prefix_1_3"]["official_outcomes"].get(outcome, 0)
            + scopes["remainder_4_6"]["official_outcomes"].get(outcome, 0)
        )


def test_missing_legacy_fields_are_null_not_zero(tmp_path: Path) -> None:
    predictions = _write_predictions(
        tmp_path / "predictions.jsonl", [_prediction("org__repo-1", patch=None, diagnostics=False)]
    )
    report = _write_json(
        tmp_path / "report.json",
        _report(["org__repo-1"], resolved=[], unresolved=[], empty=[], error=["org__repo-1"]),
    )
    analysis = analyze_paths(predictions, report)
    row = analysis["instances"][0]
    assert row["patch"]["is_empty"] is None
    assert row["patch"]["chars"] is None
    assert row["agent"]["counters"]["parse_errors"] is None
    assert analysis["summary"]["all"]["agent_metrics"]["parse_errors"]["unmeasured_count"] == 1


def test_legacy_prediction_and_trace_counters_remain_unmeasured(tmp_path: Path) -> None:
    prediction = _prediction(IDS[0], diagnostics=False, dm_steps=99, dm_parse_errors=7)
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [prediction])
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[], unresolved=[IDS[0]], empty=[], error=[]),
    )
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    _write_trace(
        trace_dir / f"{IDS[0]}.jsonl",
        IDS[0],
        actions=[("read_file", {"path": "a.py"}), ("task_complete", {})],
        metadata={},
    )

    analysis = analyze_paths(predictions, report, trace_dirs=[trace_dir])
    row = analysis["instances"][0]
    assert row["agent"]["steps"] == 2
    assert row["agent"]["counters"]["parse_errors"] is None
    assert row["agent"]["counters"]["edit_guard_blocks"] is None
    parse_metric = analysis["summary"]["all"]["agent_metrics"]["parse_errors"]
    assert parse_metric == {
        "sum": None,
        "measured_count": 0,
        "unmeasured_count": 1,
        "denominator": 1,
    }


def test_invalid_trace_never_backfills_agent_diagnostics(tmp_path: Path) -> None:
    predictions = _write_predictions(
        tmp_path / "predictions.jsonl", [_prediction(IDS[0], diagnostics=False)]
    )
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[], unresolved=[IDS[0]], empty=[], error=[]),
    )
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    _write_trace(
        trace_dir / f"{IDS[0]}.jsonl",
        IDS[0],
        actions=[("edit_file", {"path": "a.py"}), ("run_tests", {})],
        metadata={"parse_error_count": 7},
        malformed_line=True,
    )

    analysis = analyze_paths(predictions, report, trace_dirs=[trace_dir])
    row = analysis["instances"][0]
    assert row["trace"]["status"] == "invalid"
    assert row["trace"]["direct_write_calls"] is None
    assert row["trace"]["verification_gap"] is None
    assert row["agent"]["steps"] is None
    assert row["agent"]["counters"]["parse_errors"] is None
    assert analysis["summary"]["all"]["trace"]["direct_write_calls"]["measured_count"] == 0


def test_trace_runtime_mapping_fallback_and_bad_trace_isolated(tmp_path: Path) -> None:
    predictions = _write_predictions(
        tmp_path / "predictions.jsonl", [_prediction(IDS[0]), _prediction(IDS[1])]
    )
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0], IDS[1]], resolved=[IDS[0]], unresolved=[IDS[1]], empty=[], error=[]),
    )
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    _write_trace(trace_dir / "wrong-name.jsonl", IDS[0], runtime_id=IDS[0], malformed_line=True)
    _write_trace(trace_dir / f"{IDS[1]}.jsonl", IDS[1])
    # Make the second trace a legacy file with no runtime event: filename fallback is explicit.
    legacy = trace_dir / f"{IDS[1]}.jsonl"
    lines = legacy.read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if '"event": "runtime"' not in line]
    legacy.write_text("\n".join(lines) + "\n", encoding="utf-8")

    analysis = analyze_paths(predictions, report, trace_dirs=[trace_dir])
    rows = {row["instance_id"]: row for row in analysis["instances"]}
    assert rows[IDS[0]]["trace"]["status"] == "invalid"
    assert rows[IDS[0]]["trace"]["direct_write_calls"] is None
    assert rows[IDS[0]]["trace"]["verification_gap"] is None
    assert rows[IDS[1]]["trace"]["status"] == "measured"
    codes = {warning["code"] for warning in analysis["warnings"]}
    assert {"trace_bad_json", "trace_runtime_filename_mismatch", "trace_filename_fallback"} <= codes


def test_duplicate_trace_instance_is_rejected(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )
    first = tmp_path / "traces-1"
    second = tmp_path / "traces-2"
    first.mkdir()
    second.mkdir()
    _write_trace(first / f"{IDS[0]}.jsonl", IDS[0])
    _write_trace(second / f"{IDS[0]}.jsonl", IDS[0])
    with pytest.raises(AnalysisInputError, match="多个 trace"):
        analyze_paths(predictions, report, trace_dirs=[first, second])


def test_repeated_tool_signature_uses_canonical_json(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    _write_trace(
        trace_dir / f"{IDS[0]}.jsonl",
        IDS[0],
        actions=[
            ("read_file", {"path": "a.py", "line_start": 1}),
            ("read_file", {"line_start": 1, "path": "a.py"}),
        ],
    )
    analysis = analyze_paths(predictions, report, trace_dirs=[trace_dir])
    trace = analysis["instances"][0]["trace"]
    assert trace["repeated_tool_signature_count"] == 1
    assert trace["repeated_tool_call_count"] == 1


def test_append_only_trace_uses_last_complete_run_without_cross_run_counts(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    events: list[dict[str, Any]] = []
    _append_run(
        events,
        IDS[0],
        "run-one",
        actions=[("run_tests", {}), ("read_file", {"path": "a.py"})],
        status="success",
    )
    _append_run(
        events,
        IDS[0],
        "run-two",
        actions=[
            ("read_file", {"path": "a.py"}),
            ("read_file", {"path": "a.py"}),
        ],
        status="success",
    )
    trace_path = trace_dir / f"{IDS[0]}.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8"
    )

    analysis = analyze_paths(predictions, report, trace_dirs=[trace_dir])
    trace = analysis["instances"][0]["trace"]
    assert trace["status"] == "measured"
    assert trace["steps"] == 2
    assert trace["event_count"] == 7
    assert trace["repeated_tool_signature_count"] == 1
    assert trace["verification_gap"] is True
    assert any(item["code"] == "trace_multiple_runs" for item in analysis["warnings"])


def test_append_only_trace_falls_back_from_trailing_incomplete_run(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    events: list[dict[str, Any]] = []
    _append_run(
        events,
        IDS[0],
        "run-one",
        actions=[("run_tests", {})],
        status="success",
    )
    _append_run(
        events,
        IDS[0],
        "run-two",
        actions=[("read_file", {"path": "b.py"})],
        status=None,
    )
    (trace_dir / f"{IDS[0]}.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8"
    )

    analysis = analyze_paths(predictions, report, trace_dirs=[trace_dir])
    trace = analysis["instances"][0]["trace"]
    assert trace["status"] == "measured"
    assert trace["steps"] == 1
    assert trace["verification_gap"] is False
    assert any(item["code"] == "trace_trailing_incomplete_run" for item in analysis["warnings"])


def test_append_only_trace_detects_runtime_only_tail(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    events: list[dict[str, Any]] = []
    _append_run(
        events,
        IDS[0],
        "run-one",
        actions=[("run_tests", {})],
        status="success",
    )
    events.append(_run_event("run-two", "runtime", {"instance_id": IDS[0], "repo": "org/repo"}))
    (trace_dir / f"{IDS[0]}.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8"
    )

    analysis = analyze_paths(predictions, report, trace_dirs=[trace_dir])
    trace = analysis["instances"][0]["trace"]
    assert trace["status"] == "measured"
    assert trace["steps"] == 1
    assert trace["event_count"] == 5
    assert any(item["code"] == "trace_trailing_incomplete_run" for item in analysis["warnings"])


def test_input_contract_fail_fast_and_explicit_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )
    manifest = _write_json(tmp_path / "manifest.json", _manifest([IDS[0], IDS[1]]))
    with pytest.raises(AnalysisInputError, match="顺序"):
        analyze_paths(predictions, report, manifest_path=manifest)
    assert (
        main(
            [
                "--predictions",
                str(predictions),
                "--report",
                str(report),
                "--trace-dir",
                str(tmp_path / "missing"),
            ]
        )
        == 2
    )
    assert "不存在" in capsys.readouterr().err


def test_core_json_duplicates_and_report_partition_fail_fast(tmp_path: Path) -> None:
    duplicate = [_prediction(IDS[0]), _prediction(IDS[0])]
    duplicate_path = _write_predictions(tmp_path / "duplicate.jsonl", duplicate)
    valid_report = _write_json(
        tmp_path / "valid-report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )
    with pytest.raises(AnalysisInputError, match="重复 instance_id"):
        analyze_paths(duplicate_path, valid_report)

    bad_json = tmp_path / "bad.jsonl"
    bad_json.write_text('{"instance_id": "ok"}\n{bad\n', encoding="utf-8")
    with pytest.raises(AnalysisInputError, match="第 2 行"):
        analyze_paths(bad_json, valid_report)

    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    overlapping = _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[])
    overlapping["unresolved_ids"] = [IDS[0]]
    overlapping["unresolved_instances"] = 1
    overlapping["completed_ids"] = [IDS[0]]
    overlapping["completed_instances"] = 1
    overlapping_path = _write_json(tmp_path / "overlap.json", overlapping)
    with pytest.raises(AnalysisInputError, match="类别重叠"):
        analyze_paths(predictions, overlapping_path)

    bad_count = _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[])
    bad_count["resolved_instances"] = 0
    with pytest.raises(AnalysisInputError, match="长度不一致"):
        analyze_paths(predictions, _write_json(tmp_path / "bad-count.json", bad_count))

    bad_completed = _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[])
    bad_completed["completed_ids"] = []
    bad_completed["completed_instances"] = 0
    with pytest.raises(AnalysisInputError, match="completed_ids"):
        analyze_paths(predictions, _write_json(tmp_path / "bad-completed.json", bad_completed))

    incomplete_partition = _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[])
    incomplete_partition["resolved_ids"] = []
    incomplete_partition["resolved_instances"] = 0
    incomplete_partition["completed_ids"] = []
    incomplete_partition["completed_instances"] = 0
    with pytest.raises(AnalysisInputError, match="并集"):
        analyze_paths(
            predictions,
            _write_json(tmp_path / "incomplete-partition.json", incomplete_partition),
        )


def test_report_only_unknown_instance_warns_without_changing_denominator(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json",
        _report(
            [IDS[0], IDS[1]],
            resolved=[IDS[0]],
            unresolved=[IDS[1]],
            empty=[],
            error=[],
        ),
    )
    analysis = analyze_paths(predictions, report)
    assert analysis["summary"]["all"]["denominator"] == 1
    codes = {warning["code"] for warning in analysis["warnings"]}
    assert {"report_unknown_instance", "prediction_missing_instance"} <= codes


def test_prediction_missing_from_report_is_incomplete(tmp_path: Path) -> None:
    predictions = _write_predictions(
        tmp_path / "predictions.jsonl", [_prediction(IDS[0]), _prediction(IDS[1])]
    )
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )
    analysis = analyze_paths(predictions, report)
    rows = {row["instance_id"]: row for row in analysis["instances"]}
    assert rows[IDS[1]]["official"]["outcome"] == "incomplete"
    assert analysis["summary"]["all"]["official_outcomes"]["incomplete"] == 1


def test_empty_patch_with_shell_call_is_not_labeled_no_edit(tmp_path: Path) -> None:
    predictions = _write_predictions(
        tmp_path / "predictions.jsonl",
        [_prediction(IDS[0], patch="", status="max_steps_exceeded")],
    )
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[], unresolved=[], empty=[IDS[0]], error=[]),
    )
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    _write_trace(
        trace_dir / f"{IDS[0]}.jsonl",
        IDS[0],
        status="max_steps_exceeded",
        actions=[("run_shell", {"command": "python rewrite.py"})],
    )
    analysis = analyze_paths(predictions, report, trace_dirs=[trace_dir])
    assert "empty_patch" in analysis["instances"][0]["failure_labels"]
    assert "no_edit" not in analysis["instances"][0]["failure_labels"]


def test_output_paths_never_overwrite_inputs(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    original = predictions.read_bytes()
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )
    with pytest.raises(AnalysisInputError, match="覆盖"):
        analyze_paths(predictions, report, json_output=predictions)
    assert predictions.read_bytes() == original
    with pytest.raises(AnalysisInputError, match="同一个文件"):
        analyze_paths(
            predictions, report, json_output=tmp_path / "same", markdown_output=tmp_path / "same"
        )


def test_cli_is_strictly_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import swebench_verified.predict as predict_module

    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("offline analyzer attempted external execution")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(predict_module, "docker_preflight", forbidden)
    monkeypatch.setattr(predict_module, "build_client", forbidden)
    monkeypatch.setattr(predict_module, "predict_one", forbidden)
    json_output = tmp_path / "analysis.json"
    markdown_output = tmp_path / "analysis.md"

    assert (
        main(
            [
                "--predictions",
                str(predictions),
                "--report",
                str(report),
                "--json",
                str(json_output),
                "--markdown",
                str(markdown_output),
            ]
        )
        == 0
    )
    capsys.readouterr()
    parsed = json.loads(json_output.read_text(encoding="utf-8"))
    assert parsed["mode"] == "swebench_failure_analysis"
    assert "# SWE-bench 离线失败分析" in markdown_output.read_text(encoding="utf-8")


def test_failure_text_redacts_secrets_and_test_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANALYZER_SECRET_TOKEN", "env-secret-value-123")
    secret_message = (
        "sk-live-abcdefghijklmnop env-secret-value-123 "
        "Bearer abcdefghijklmnop https://example.test/?access_token=url-secret "
        "FAIL_TO_PASS hidden-test"
    )
    predictions = _write_predictions(
        tmp_path / "predictions.jsonl",
        [
            _prediction(
                IDS[0], diagnostics=False, status="agent_exception", dm_failure=secret_message
            )
        ],
    )
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[], unresolved=[], empty=[], error=[IDS[0]]),
    )
    serialized = render_json(analyze_paths(predictions, report))
    markdown = render_markdown(analyze_paths(predictions, report))
    for value in ("sk-live-abcdefghijklmnop", "env-secret-value-123", "url-secret", "hidden-test"):
        assert value not in serialized
        assert value not in markdown
    assert "<redacted-secret>" in serialized
    assert "<redacted-test-field>" in serialized


def test_deterministic_private_outputs_and_aggregation_denominators(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    first = analyze_paths(
        bundle["predictions"],
        bundle["report"],
        manifest_path=bundle["manifest"],
        trace_dirs=[bundle["trace_dir"]],
    )
    second = analyze_paths(
        bundle["predictions"],
        bundle["report"],
        manifest_path=bundle["manifest"],
        trace_dirs=[bundle["trace_dir"]],
    )
    assert render_json(first) == render_json(second)
    assert render_markdown(first) == render_markdown(second)
    serialized = render_json(first)
    assert "hidden-f2p" not in serialized
    assert "observation" not in serialized
    assert sum(bucket["denominator"] for bucket in first["summary"]["by_repo"].values()) == 6
    assert sum(bucket["denominator"] for bucket in first["summary"]["by_difficulty"].values()) == 6
    assert first["summary"]["by_failure_label"]["empty_patch"]["denominator"] == 6


def test_archived_crossrepo_50_regression_without_traces() -> None:
    root = Path(__file__).resolve().parents[1]
    analysis = analyze_paths(
        root / "bench_reports/swebench-verified-crossrepo-50-predictions-20260806.jsonl",
        root / "bench_reports/swebench-verified-crossrepo-50-20260806.json",
        manifest_path=root / "bench_reports/swebench-verified-crossrepo-50-selection-20260806.json",
        prefix_count=20,
    )
    assert analysis["summary"]["all"]["official_outcomes"] == {
        "resolved": 21,
        "unresolved": 22,
        "empty_patch": 7,
        "harness_error": 0,
        "incomplete": 0,
        "unknown": 0,
    }
    assert analysis["summary"]["prefix_1_20"]["official_outcomes"] == {
        "resolved": 11,
        "unresolved": 7,
        "empty_patch": 2,
        "harness_error": 0,
        "incomplete": 0,
        "unknown": 0,
    }
    assert analysis["summary"]["remainder_21_50"]["official_outcomes"] == {
        "resolved": 10,
        "unresolved": 15,
        "empty_patch": 5,
        "harness_error": 0,
        "incomplete": 0,
        "unknown": 0,
    }
    assert analysis["summary"]["all"]["patch"]["nonempty_count"] == 43
    assert analysis["summary"]["all"]["agent_outcomes"] == {
        "success": 27,
        "max_steps": 23,
        "exception": 0,
        "unknown": 0,
    }
    assert analysis["summary"]["all"]["agent_metrics"]["steps"]["sum"] == 1757
    assert analysis["summary"]["all"]["agent_metrics"]["parse_errors"]["sum"] == 117
    assert analysis["summary"]["all"]["agent_metrics"]["repeat_search_blocks"]["sum"] == 49


def test_report_without_required_id_arrays_fails_fast(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json", {"submitted_instances": 1, "resolved_instances": 1}
    )
    with pytest.raises(AnalysisInputError, match="逐题 ID 数组"):
        analyze_paths(predictions, report)


def test_report_partial_id_arrays_fails_fast(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[])
    del report["error_ids"]
    report_path = _write_json(tmp_path / "partial-report.json", report)
    with pytest.raises(AnalysisInputError, match="error_ids"):
        analyze_paths(predictions, report_path)


def test_harness_detail_only_requires_f2p_and_p2p_axes(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[IDS[0]], unresolved=[], empty=[], error=[]),
    )
    detail_dir = tmp_path / "details" / IDS[0]
    detail_dir.mkdir(parents=True)
    _write_json(
        detail_dir / "report.json",
        {
            IDS[0]: {
                "patch_successfully_applied": True,
                "tests_status": {
                    "FAIL_TO_PASS": {"failure": []},
                    "PASS_TO_PASS": {"failure": []},
                },
            }
        },
    )
    analysis = analyze_paths(predictions, report, harness_log_dir=tmp_path / "details")
    assert analysis["instances"][0]["harness_detail"]["status"] == "all_passed"


def test_bad_harness_detail_is_invalid_not_missing(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "predictions.jsonl", [_prediction(IDS[0])])
    report = _write_json(
        tmp_path / "report.json",
        _report([IDS[0]], resolved=[], unresolved=[IDS[0]], empty=[], error=[]),
    )
    detail_dir = tmp_path / "details" / IDS[0]
    detail_dir.mkdir(parents=True)
    (detail_dir / "report.json").write_text("{bad json\n", encoding="utf-8")
    analysis = analyze_paths(predictions, report, harness_log_dir=tmp_path / "details")
    assert analysis["instances"][0]["harness_detail"]["status"] == "invalid"
    assert analysis["summary"]["all"]["harness_details"]["invalid"] == 1
    assert any(item["code"] == "harness_detail_bad_json" for item in analysis["warnings"])
