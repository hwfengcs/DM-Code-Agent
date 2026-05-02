from pathlib import Path

from dm_agent.benchmarks.cli import main as bench_main
from dm_agent.benchmarks.runner import prepare_workspace, run_hidden_tests
from dm_agent.benchmarks.tasks import get_coding_tasks


def test_coding_benchmark_manifest_is_hidden_test_based():
    tasks = get_coding_tasks()

    assert len(tasks) >= 6
    assert all(task.setup_files for task in tasks)
    assert all(task.hidden_files for task in tasks)
    assert all("Hidden tests will be added" in task.prompt for task in tasks)


def test_coding_benchmark_cli_lists_without_api_key():
    assert bench_main(["--list"]) == 0


def test_hidden_tests_fail_on_initial_slugify_workspace(tmp_path):
    task = get_coding_tasks(["slugify_cleanup"])[0]
    prepare_workspace(task, tmp_path, include_hidden=True)

    result = run_hidden_tests(task, tmp_path)

    assert result.returncode != 0
    assert "test_hidden_slugify" in result.stdout


def test_hidden_tests_pass_for_known_slugify_solution(tmp_path):
    task = get_coding_tasks(["slugify_cleanup"])[0]
    prepare_workspace(task, tmp_path, include_hidden=True)
    Path(tmp_path / "text_utils.py").write_text(
        (
            "import re\n\n\n"
            "def slugify(value: str) -> str:\n"
            "    value = value.strip().lower()\n"
            '    value = re.sub(r"[^a-z0-9]+", "-", value)\n'
            '    return re.sub(r"-+", "-", value).strip("-")\n'
        ),
        encoding="utf-8",
    )

    result = run_hidden_tests(task, tmp_path)

    assert result.returncode == 0
