import json

import pytest

from dm_agent.evals.cli import main as eval_main
from dm_agent.evals.gate import evaluate_gate
from dm_agent.evals.gate import main as gate_main
from dm_agent.evals.models import EvalResult
from dm_agent.evals.real_runner import get_real_tasks
from dm_agent.evals.runner import EvalVariant, run_suite, summarize_results
from dm_agent.evals.tasks import get_builtin_tasks


def test_builtin_eval_suite_runs_full_variant():
    report = run_suite(
        variants=[EvalVariant("full", True, True, True)],
        task_ids=["direct_finish", "json_repair", "tool_failure_replan"],
    )

    summary = report["summary"]["variants"]["full"]
    assert summary["tasks"] == 3
    assert summary["success_rate"] == 1.0
    assert summary["recovery_events"] >= 2


def test_eval_ablation_runs_all_builtin_tasks():
    tasks = get_builtin_tasks()
    report = run_suite(tasks=tasks)

    assert report["summary"]["total_runs"] == len(tasks) * 4
    assert "full" in report["summary"]["variants"]
    assert report["summary"]["variants"]["full"]["success_rate"] == 1.0


def test_eval_cli_writes_reports(tmp_path):
    json_path = tmp_path / "report.json"
    md_path = tmp_path / "report.md"

    exit_code = eval_main(
        [
            "--variant",
            "full",
            "--task",
            "direct_finish",
            "--output",
            str(json_path),
            "--markdown",
            str(md_path),
        ]
    )

    assert exit_code == 0
    assert json_path.exists()
    assert md_path.exists()
    assert "Ablation Summary" in md_path.read_text(encoding="utf-8")


def test_real_eval_manifest_is_explicit_and_keyless():
    tasks = get_real_tasks()

    assert tasks
    assert all(task.task_id.startswith("real_") for task in tasks)
    assert all(task.agent_responses == [] for task in tasks)
    assert any("recovery" in task.tags for task in tasks)


def test_real_eval_cli_lists_without_api_key():
    assert eval_main(["--real", "--list"]) == 0


def _eval_result(task_id, *, success, metadata=None, variant="full"):
    return EvalResult(
        task_id=task_id,
        task_name=task_id,
        variant=variant,
        success=success,
        final_answer="",
        failure_reason="" if success else "failed validation",
        actions=["finish"],
        steps_count=1,
        tool_calls=0,
        duration_seconds=0.0,
        prompt_chars=10,
        completion_chars=5,
        estimated_tokens=4,
        estimated_cost_usd=0.0,
        metadata=metadata or {},
    )


def test_summarize_results_recovery_rate_math():
    results = [
        _eval_result("a", success=True, metadata={"tool_error_count": 1}),
        _eval_result("b", success=False, metadata={"parse_error_count": 2}),
        _eval_result("c", success=True),
    ]
    summary = summarize_results(results)
    variant = summary["variants"]["full"]

    assert variant["runs_with_failures"] == 2
    assert variant["recovered_runs"] == 1
    assert variant["recovery_success_rate"] == pytest.approx(0.5)


def test_summarize_results_recovery_rate_none_without_failures():
    summary = summarize_results([_eval_result("a", success=True)])
    assert summary["variants"]["full"]["recovery_success_rate"] is None


def test_summarize_results_by_tag_uses_task_tags():
    tasks = [task for task in get_builtin_tasks() if task.task_id in {"direct_finish"}]
    results = [_eval_result("direct_finish", success=True)]
    summary = summarize_results(results, tasks=tasks)

    assert summary["by_tag"]["control"]["runs"] == 1
    assert summary["by_tag"]["control"]["success_rate"] == 1.0


def test_summarize_results_tolerates_legacy_metadata():
    # v2.0-era results lack the new counters entirely; aggregation must not raise.
    legacy = _eval_result("old", success=True, metadata={"status": "success"})
    summary = summarize_results([legacy])
    assert summary["variants"]["full"]["runs_with_failures"] == 0


def test_new_guard_and_truncation_eval_tasks_pass_all_variants():
    report = run_suite(task_ids=["truncated_read_pagination", "edit_guard_reread"])

    assert report["summary"]["overall_success_rate"] == 1.0
    assert report["summary"]["total_runs"] == 8  # 2 tasks x 4 variants


def test_gate_passes_green_report(tmp_path, capsys):
    report = run_suite(task_ids=["direct_finish"])
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    assert gate_main([str(path), "--min-success-rate", "1.0"]) == 0


def test_gate_fails_below_threshold():
    report = {
        "summary": {
            "overall_success_rate": 0.5,
            "variants": {"full": {"success_rate": 0.5}},
        },
        "results": [
            {"variant": "full", "task_id": "broken", "success": False, "failure_reason": "boom"}
        ],
    }
    violations = evaluate_gate(report, min_success_rate=1.0, min_variant_rate=1.0)

    assert any("overall_success_rate" in violation for violation in violations)
    assert any("broken" in violation for violation in violations)


def test_gate_rejects_unreadable_report(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert gate_main([str(bad)]) == 2
    assert gate_main([str(tmp_path / "missing.json")]) == 2
