"""Offline regressions for nested report fields and SWE preparation isolation."""

import json
from types import SimpleNamespace

import pytest

from dm_agent.benchmarks.economics import main as economics_main
from dm_agent.benchmarks.economics import summarize_report
from swebench_verified import dataset, predict


@pytest.mark.parametrize("field", ["task_id", "variant"])
@pytest.mark.parametrize("value", [None, [], 1, ""])
def test_optional_economics_identity_must_still_be_a_string(field, value):
    report = {"results": [{"success": True, field: value}]}
    with pytest.raises(ValueError, match=field):
        summarize_report(report)


@pytest.mark.parametrize(
    "extra",
    [
        {"token_economics": [1]},
        {"summary": {"overall_pass_rate_ci_95": {"low": [], "high": 1}}},
        {"summary": {"overall_pass_rate_ci_95": {"low": 0.9, "high": 0.1}}},
        {"summary": {"overall_pass_rate_ci_95": {"low": 0, "high": 2}}},
    ],
)
def test_invalid_nested_economics_input_returns_error_without_output(tmp_path, extra):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"results": [{"success": True}], **extra}), encoding="utf-8")
    output_json, output_md = tmp_path / "output.json", tmp_path / "output.md"
    assert (
        economics_main(
            [str(path), "--output-json", str(output_json), "--output-md", str(output_md)]
        )
        == 2
    )
    assert not output_json.exists() and not output_md.exists()


def test_replaced_swe_cache_preserves_both_original_files(tmp_path, monkeypatch):
    cache = tmp_path / "instances.jsonl"
    metadata = cache.with_suffix(".meta.json")
    cache.write_bytes(b"null\n")
    metadata.write_bytes(b"null\n")
    row = {"instance_id": "org__repo-1", "repo": "org/repo"}
    monkeypatch.setattr(dataset, "_fetch_page", lambda *args: ([row], 1))
    assert dataset.fetch_instances(cache_path=cache)[0]["instance_id"] == row["instance_id"]
    assert [path.read_bytes() for path in tmp_path.glob("instances.jsonl.*.bak")] == [b"null\n"]
    assert [path.read_bytes() for path in tmp_path.glob("instances.meta.json.*.bak")] == [b"null\n"]


def test_swe_preparation_removes_only_its_own_unique_containers(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(predict, "ensure_image", lambda instance_id: "image")

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(predict, "_run", run)
    monkeypatch.setattr(predict, "_copy_workspace_from_container", lambda *args: None)
    monkeypatch.setattr(predict, "_assert_git_root", lambda *args: None)
    monkeypatch.setattr(predict, "_neutralize_windows_git_noise", lambda *args: None)
    for index in range(2):
        predict.materialize_workspace("org__repo-1", tmp_path / str(index))
    created = [command[3] for command in calls if command[1] == "create"]
    removed = [command[3] for command in calls if command[1] == "rm"]
    assert len(set(created)) == 2
    assert removed == created
    assert [command[1] for command in calls] == ["create", "rm", "create", "rm"]
