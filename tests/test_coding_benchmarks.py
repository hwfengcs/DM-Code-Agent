from pathlib import Path

import pytest

from dm_agent.benchmarks import runner as runner_module
from dm_agent.benchmarks.cli import main as bench_main
from dm_agent.benchmarks.economics import build_economics_report, render_markdown
from dm_agent.benchmarks.models import BenchmarkRunConfig, CodingBenchResult, CommandResult
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


def test_benchmark_feature_flags_parse_without_api_key():
    assert (
        bench_main(
            [
                "--list",
                "--enable-rag",
                "--rag-top-k",
                "3",
                "--enable-critic",
                "--self-consistency-runs",
                "2",
                "--self-consistency-strategy",
                "critic_score",
            ]
        )
        == 0
    )


def test_swebench_self_consistency_is_explicitly_frozen(
    capsys: pytest.CaptureFixture[str],
):
    assert (
        bench_main(
            [
                "--suite",
                "swebench_lite",
                "--self-consistency-runs",
                "2",
                "--snapshot-path",
                "missing.jsonl",
            ]
        )
        == 2
    )
    assert "self-consistency is intentionally not wired" in capsys.readouterr().err


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


def _bench_result(task_id: str, *, success: bool, final_answer: str, tokens: int):
    return CodingBenchResult(
        task_id=task_id,
        task_name="Task",
        variant="full",
        success=success,
        failure_reason="" if success else "failed",
        final_answer=final_answer,
        actions=["finish"],
        steps_count=1,
        tool_calls=0,
        duration_seconds=0.1,
        prompt_chars=10,
        completion_chars=5,
        estimated_tokens=tokens,
        estimated_cost_usd=tokens / 1000,
        request_count=1,
        metadata={"status": "success" if success else "failure"},
        hidden_test=CommandResult(["pytest"], 0 if success else 1, "", "", 0.1),
    )


def test_benchmark_report_includes_default_off_feature_flags(monkeypatch: pytest.MonkeyPatch):
    def fake_run_benchmark_task(task, variant, config, *, repeat_index=0, suite="coding"):
        return _bench_result(task.task_id, success=True, final_answer="ok", tokens=100)

    monkeypatch.setattr(runner_module, "run_benchmark_task", fake_run_benchmark_task)
    task = get_coding_tasks(["slugify_cleanup"])[0]

    report = runner_module.run_benchmark_suite(
        tasks=[task],
        config=BenchmarkRunConfig(
            enable_rag=True,
            rag_top_k=3,
            enable_critic=True,
            self_consistency_runs=2,
            self_consistency_strategy="critic_score",
        ),
    )

    assert report["rag"]["enabled"] is True
    assert report["rag"]["top_k"] == 3
    assert report["critic"]["enabled"] is True
    assert report["self_consistency"]["runs"] == 2
    assert report["self_consistency"]["strategy"] == "critic_score"


def test_self_consistency_benchmark_uses_fresh_candidate_results(
    monkeypatch: pytest.MonkeyPatch,
):
    task = get_coding_tasks(["slugify_cleanup"])[0]
    candidates = [
        _bench_result(task.task_id, success=False, final_answer="bad", tokens=200),
        _bench_result(task.task_id, success=True, final_answer="good", tokens=300),
    ]

    def fake_run_in_workspace(*args, **kwargs):
        repeat_index = kwargs["repeat_index"]
        return candidates[repeat_index]

    monkeypatch.setattr(runner_module, "_run_benchmark_task_in_workspace", fake_run_in_workspace)

    result = runner_module.run_benchmark_task(
        task,
        runner_module.DEFAULT_BENCH_VARIANTS[0],
        BenchmarkRunConfig(self_consistency_runs=2, self_consistency_strategy="test_pass"),
    )

    assert result.success is True
    assert result.final_answer == "good"
    assert result.estimated_tokens == 500
    assert result.metadata["self_consistency"]["runs"] == 2
    assert result.metadata["self_consistency"]["selected_index"] == 2


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


def test_maintenance_hidden_tests_fail_on_initial_cli_docs_workspace(tmp_path):
    task = get_maintenance_tasks(["cli_config_docs_contract"])[0]
    prepare_workspace(task, tmp_path, include_hidden=True)

    result = run_hidden_tests(task, tmp_path)

    assert result.returncode != 0
    assert "test_all_config_options_are_documented_and_sorted" in result.stdout


def test_maintenance_hidden_tests_pass_for_known_cli_docs_solution(tmp_path):
    task = get_maintenance_tasks(["cli_config_docs_contract"])[0]
    prepare_workspace(task, tmp_path, include_hidden=True)
    Path(tmp_path / "cli_docs.py").write_text(
        (
            "CONFIG_OPTIONS = [\n"
            "    {\n"
            '        "flag": "--provider",\n'
            '        "env": "DM_PROVIDER",\n'
            '        "default": "deepseek",\n'
            '        "description": "LLM provider name.",\n'
            "    },\n"
            "    {\n"
            '        "flag": "--timeout",\n'
            '        "env": "DM_TIMEOUT",\n'
            '        "default": 120,\n'
            '        "description": "Provider request timeout in seconds.",\n'
            "    },\n"
            "    {\n"
            '        "flag": "--model",\n'
            '        "env": "DM_MODEL",\n'
            '        "default": "deepseek-chat",\n'
            '        "description": "Model identifier passed to the provider.",\n'
            "    },\n"
            "    {\n"
            '        "flag": "--retries",\n'
            '        "env": "DM_RETRIES",\n'
            '        "default": 2,\n'
            '        "description": "Retry count for transient provider failures.",\n'
            "    },\n"
            "]\n\n\n"
            "def render_config_table(options=None):\n"
            "    options = options or CONFIG_OPTIONS\n"
            "    lines = [\n"
            '        "| Option | Env | Default | Description |",\n'
            '        "| --- | --- | --- | --- |",\n'
            "    ]\n"
            "    for item in sorted(options, key=lambda option: option['flag']):\n"
            "        lines.append(\n"
            "            f\"| `{item['flag']}` | `{item['env']}` | "
            "`{item['default']}` | {item['description']} |\"\n"
            "        )\n"
            '    return "\\n".join(lines)\n'
        ),
        encoding="utf-8",
    )
    table = (
        "| Option | Env | Default | Description |\n"
        "| --- | --- | --- | --- |\n"
        "| `--model` | `DM_MODEL` | `deepseek-chat` | Model identifier passed to the provider. |\n"
        "| `--provider` | `DM_PROVIDER` | `deepseek` | LLM provider name. |\n"
        "| `--retries` | `DM_RETRIES` | `2` | Retry count for transient provider failures. |\n"
        "| `--timeout` | `DM_TIMEOUT` | `120` | Provider request timeout in seconds. |"
    )
    Path(tmp_path / "docs" / "configuration.md").write_text(
        (
            "# Configuration\n\n"
            "DM-Code-Agent can be configured with CLI flags or environment variables.\n\n"
            "<!-- CONFIG_TABLE -->\n"
            f"{table}\n"
            "<!-- /CONFIG_TABLE -->\n"
        ),
        encoding="utf-8",
    )
    Path(tmp_path / "tests" / "test_public_cli_docs.py").write_text(
        (
            "from pathlib import Path\n\n"
            "from cli_docs import CONFIG_OPTIONS, render_config_table\n\n\n"
            "def test_config_table_mentions_every_option():\n"
            "    table = render_config_table()\n"
            "    for item in CONFIG_OPTIONS:\n"
            "        assert f\"`{item['flag']}`\" in table\n\n\n"
            "def test_docs_embed_generated_table():\n"
            "    docs = Path('docs/configuration.md').read_text(encoding='utf-8')\n"
            "    assert render_config_table() in docs\n"
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
