from pathlib import Path

from dm_agent.benchmarks.cli import main as bench_main
from dm_agent.benchmarks.economics import build_economics_report, render_markdown
from dm_agent.benchmarks.runner import prepare_workspace, run_hidden_tests, write_markdown_report
from dm_agent.benchmarks.tasks import get_benchmark_tasks, get_coding_tasks, get_maintenance_tasks


def test_coding_benchmark_manifest_is_hidden_test_based():
    tasks = get_coding_tasks()

    assert len(tasks) >= 6
    assert all(task.setup_files for task in tasks)
    assert all(task.hidden_files for task in tasks)
    assert all("Hidden tests will be added" in task.prompt for task in tasks)


def test_coding_benchmark_cli_lists_without_api_key():
    assert bench_main(["--list"]) == 0


def test_maintenance_benchmark_manifest_is_realistic_and_keyless():
    tasks = get_maintenance_tasks()

    assert len(tasks) >= 4
    assert all(task.setup_files for task in tasks)
    assert all(task.hidden_files for task in tasks)
    assert all("Hidden tests will be added" in task.prompt for task in tasks)
    assert any(task.required_changed_files for task in tasks)
    assert bench_main(["--suite", "maintenance", "--list"]) == 0


def test_benchmark_suite_selector_filters_tasks():
    tasks = get_benchmark_tasks("maintenance", ["config_precedence"])

    assert [task.task_id for task in tasks] == ["config_precedence"]


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


def test_maintenance_hidden_tests_fail_on_initial_config_workspace(tmp_path):
    task = get_maintenance_tasks(["config_precedence"])[0]
    prepare_workspace(task, tmp_path, include_hidden=True)

    result = run_hidden_tests(task, tmp_path)

    assert result.returncode != 0
    assert "test_cli_overrides_env_and_file" in result.stdout


def test_maintenance_hidden_tests_pass_for_known_config_solution(tmp_path):
    task = get_maintenance_tasks(["config_precedence"])[0]
    prepare_workspace(task, tmp_path, include_hidden=True)
    Path(tmp_path / "config_loader.py").write_text(
        (
            "import os\n\n"
            'DEFAULTS = {"timeout": 30, "debug": False, "retries": 2}\n\n\n'
            "def _bool(value):\n"
            "    if isinstance(value, bool):\n"
            "        return value\n"
            "    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}\n\n\n"
            "def load_config(file_config=None, env=None, cli_args=None):\n"
            "    env = env or os.environ\n"
            "    config = DEFAULTS.copy()\n"
            "    config.update(file_config or {})\n"
            "    if 'DM_TIMEOUT' in env:\n"
            "        config['timeout'] = env['DM_TIMEOUT']\n"
            "    if 'DM_DEBUG' in env:\n"
            "        config['debug'] = env['DM_DEBUG']\n"
            "    config.update(cli_args or {})\n"
            "    config['timeout'] = int(config['timeout'])\n"
            "    config['debug'] = _bool(config['debug'])\n"
            "    return config\n"
        ),
        encoding="utf-8",
    )

    result = run_hidden_tests(task, tmp_path)

    assert result.returncode == 0


def test_benchmark_markdown_report_includes_run_details(tmp_path):
    report_path = tmp_path / "bench.md"
    report = {
        "suite": "maintenance",
        "summary": {
            "total_runs": 1,
            "overall_pass_rate": 1.0,
            "overall_hidden_test_pass_rate": 1.0,
            "overall_agent_completion_rate": 1.0,
            "variants": {
                "full": {
                    "tasks": 1,
                    "successes": 1,
                    "pass_rate": 1.0,
                    "hidden_test_pass_rate": 1.0,
                    "agent_completion_rate": 1.0,
                    "avg_steps": 2,
                    "avg_tool_calls": 1,
                    "avg_changed_files": 1,
                    "avg_estimated_tokens": 100,
                    "total_requests": 2,
                }
            },
        },
        "results": [
            {
                "variant": "full",
                "task_id": "config_precedence",
                "success": True,
                "failure_reason": "",
                "changed_files": ["config_loader.py"],
                "metadata": {"trace_path": "traces/config.jsonl"},
                "hidden_test": {"returncode": 0},
            }
        ],
    }

    write_markdown_report(report, report_path)

    text = report_path.read_text(encoding="utf-8")
    assert "Run Details" in text
    assert "Cost/success" in text
    assert "`config_loader.py`" in text
    assert "`traces/config.jsonl`" in text


def test_benchmark_economics_report_is_deterministic_and_keyless():
    report = {
        "suite": "maintenance",
        "provider": "scripted",
        "model": "fake",
        "token_economics": {"cost_per_1k_tokens": 0.002},
        "summary": {
            "total_runs": 2,
            "overall_pass_rate": 0.5,
            "total_estimated_tokens": 3000,
        },
        "results": [
            {"success": True, "estimated_tokens": 1000},
            {"success": False, "estimated_tokens": 2000},
        ],
    }

    economics = build_economics_report([report], labels=["scripted-smoke"])

    entry = economics["entries"][0]
    assert entry["label"] == "scripted-smoke"
    assert entry["successes"] == 1
    assert entry["total_estimated_tokens"] == 3000
    assert entry["estimated_cost_usd"] == 0.006
    assert entry["cost_per_success_usd"] == 0.006
    markdown = render_markdown(economics)
    assert "Benchmark Token Economics" in markdown
    assert "scripted-smoke" in markdown
