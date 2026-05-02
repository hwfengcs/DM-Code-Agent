from dm_agent.evals.cli import main as eval_main
from dm_agent.evals.real_runner import get_real_tasks
from dm_agent.evals.runner import EvalVariant, run_suite
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
