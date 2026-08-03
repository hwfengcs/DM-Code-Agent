import json

import pytest

from dm_agent.benchmarks.score_diff import (
    NOISE_FLIP_THRESHOLD,
    compare_reports,
    render_markdown,
)
from dm_agent.benchmarks.score_diff import main as score_diff_main
from dm_agent.benchmarks.tasks import get_benchmark_tasks


def _report(outcomes, *, signature="sig-a", tokens=1000, cost=0.01):
    """outcomes: {task_id: success}，单一 variant。"""
    return {
        "manifest": {"suite_signature": signature},
        "results": [
            {
                "task_id": task_id,
                "variant": "full",
                "success": success,
                "estimated_tokens": tokens,
                "estimated_cost_usd": cost,
            }
            for task_id, success in outcomes.items()
        ],
    }


def test_all_suite_is_coding_plus_maintenance_without_duplicate_ids():
    coding = get_benchmark_tasks("coding")
    maintenance = get_benchmark_tasks("maintenance")
    combined = get_benchmark_tasks("all")

    assert len(combined) == len(coding) + len(maintenance)
    ids = [task.task_id for task in combined]
    assert len(ids) == len(set(ids))


def test_compare_reports_lists_fixes_and_regressions_separately():
    left = _report({"a": True, "b": False, "c": False})
    right = _report({"a": False, "b": True, "c": False})

    comparison = compare_reports(left, right)

    assert comparison.comparable is True
    assert comparison.total == 3
    assert [f.task_id for f in comparison.fixes] == ["b"]
    assert [f.task_id for f in comparison.regressions] == ["a"]
    # 一修一坏，总分不变——正是「总分掩盖回归」的场景。
    assert comparison.pass_rate_delta == pytest.approx(0.0)
    assert comparison.flip_count == 2


def test_regression_is_surfaced_even_when_pass_rate_improves():
    left = _report({"a": True, "b": False, "c": False, "d": False})
    right = _report({"a": False, "b": True, "c": True, "d": True})

    comparison = compare_reports(left, right)

    assert comparison.pass_rate_delta > 0
    assert [f.task_id for f in comparison.regressions] == ["a"]
    markdown = render_markdown(comparison)
    assert "从通过变为失败" in markdown
    assert "## Regressed (pass → fail)" in markdown


def test_single_flip_is_reported_as_within_noise():
    left = _report({f"t{i}": i < 6 for i in range(13)})
    right = _report({f"t{i}": i < 7 for i in range(13)})

    comparison = compare_reports(left, right)

    assert comparison.flip_count == 1
    assert comparison.within_noise is True
    assert comparison.per_task_points == pytest.approx(100 / 13)
    markdown = render_markdown(comparison)
    assert "在噪声范围内" in markdown
    assert "不构成策略有效的证据" in markdown


def test_enough_flips_is_not_reported_as_noise():
    left = _report({f"t{i}": False for i in range(13)})
    right = _report({f"t{i}": i < NOISE_FLIP_THRESHOLD + 1 for i in range(13)})

    comparison = compare_reports(left, right)

    assert comparison.flip_count > NOISE_FLIP_THRESHOLD
    assert comparison.within_noise is False
    assert "在噪声范围内" not in render_markdown(comparison)


def test_mismatched_suite_signature_refuses_to_compare():
    left = _report({"a": True}, signature="sig-a")
    right = _report({"a": False}, signature="sig-b")

    comparison = compare_reports(left, right)

    assert comparison.comparable is False
    assert "任务集不同" in comparison.incomparable_reason
    assert "无法对比" in render_markdown(comparison)


def test_repeated_runs_only_count_as_passing_when_every_repeat_passed():
    left = _report({"a": True})
    right = {
        "manifest": {"suite_signature": "sig-a"},
        "results": [
            {"task_id": "a", "variant": "full", "success": True, "estimated_tokens": 1},
            {"task_id": "a", "variant": "full", "success": False, "estimated_tokens": 1},
        ],
    }

    comparison = compare_reports(left, right)

    assert comparison.right_passed == 0
    assert [f.task_id for f in comparison.regressions] == ["a"]


def test_token_and_cost_totals_are_carried_into_the_comparison():
    left = _report({"a": True}, tokens=1000, cost=0.02)
    right = _report({"a": True}, tokens=1500, cost=0.03)

    comparison = compare_reports(left, right)

    assert comparison.left_tokens == 1000
    assert comparison.right_tokens == 1500
    assert comparison.right_cost_usd == pytest.approx(0.03)
    assert "+50.0%" in render_markdown(comparison)


def test_cli_exits_nonzero_on_regression_and_zero_otherwise(tmp_path, capsys):
    left_path = tmp_path / "before.json"
    right_path = tmp_path / "after.json"
    left_path.write_text(json.dumps(_report({"a": True, "b": False})), encoding="utf-8")

    right_path.write_text(json.dumps(_report({"a": True, "b": True})), encoding="utf-8")
    assert score_diff_main([str(left_path), str(right_path)]) == 0

    right_path.write_text(json.dumps(_report({"a": False, "b": False})), encoding="utf-8")
    assert score_diff_main([str(left_path), str(right_path)]) == 1
    assert "Regressed" in capsys.readouterr().out


def test_cli_json_output_is_machine_readable(tmp_path, capsys):
    left_path = tmp_path / "before.json"
    right_path = tmp_path / "after.json"
    left_path.write_text(json.dumps(_report({"a": False})), encoding="utf-8")
    right_path.write_text(json.dumps(_report({"a": True})), encoding="utf-8")

    assert score_diff_main([str(left_path), str(right_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["comparable"] is True
    assert payload["fixes"] == [{"task_id": "a", "variant": "full"}]
    assert payload["within_noise"] is True
