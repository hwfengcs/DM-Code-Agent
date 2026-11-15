from __future__ import annotations

import json
import random
from collections import Counter
from typing import Any

import pytest

from swebench_verified import dataset, run
from swebench_verified.selection import (
    build_selection_manifest,
    normalize_difficulty,
    select_instances,
)


def _row(
    instance_id: str,
    repo: str,
    difficulty: str | None,
    *,
    problem_statement: str = "secret issue",
) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "repo": repo,
        "base_commit": f"commit-{instance_id}",
        "problem_statement": problem_statement,
        "version": "1",
        "difficulty": difficulty,
        "FAIL_TO_PASS": '["secret::f2p"]',
        "PASS_TO_PASS": '["secret::p2p"]',
    }


def _candidates() -> list[dict[str, Any]]:
    return [
        _row("alpha-1", "org/alpha", "<15 min fix"),
        _row("alpha-2", "org/alpha", "15 min - 1 hour"),
        _row("alpha-3", "org/alpha", "1-4 hours"),
        _row("alpha-4", "org/alpha", "unexpected"),
        _row("beta-1", "org/beta", "<15 min fix"),
        _row("beta-2", "org/beta", "15 min - 1 hour"),
        _row("beta-3", "org/beta", None),
        _row("gamma-1", "org/gamma", "1-4 hours"),
        _row("gamma-2", "org/gamma", ">4 hours"),
    ]


def test_fetch_instances_pages_full_dataset_and_marks_cache_complete(tmp_path, monkeypatch):
    rows = [_row(f"repo-{index}", "org/repo", "<15 min fix") for index in range(205)]
    calls: list[tuple[int, int]] = []

    def fetch_page(offset: int, length: int) -> tuple[list[dict[str, Any]], int]:
        calls.append((offset, length))
        return rows[offset : offset + length], len(rows)

    monkeypatch.setattr(dataset, "_fetch_page", fetch_page)
    cache = tmp_path / "instances.jsonl"

    instances = dataset.fetch_instances(cache_path=cache)

    assert instances == rows
    assert calls == [(0, 100), (100, 100), (200, 100)]
    metadata = json.loads((tmp_path / "instances.meta.json").read_text(encoding="utf-8"))
    assert metadata["complete"] is True
    assert metadata["row_count"] == 205


def test_legacy_partial_cache_is_not_used_for_selection(tmp_path, monkeypatch):
    cache = tmp_path / "instances.jsonl"
    cache.write_text(json.dumps(_row("legacy-1", "org/legacy", "<15 min fix")) + "\n")
    fresh = [
        _row("alpha-1", "org/alpha", "<15 min fix"),
        _row("beta-1", "org/beta", "1-4 hours"),
    ]
    calls = 0

    def fetch_page(offset: int, _length: int) -> tuple[list[dict[str, Any]], int]:
        nonlocal calls
        calls += 1
        return fresh[offset:], len(fresh)

    monkeypatch.setattr(dataset, "_fetch_page", fetch_page)

    assert dataset.fetch_instances(cache_path=cache) == fresh
    assert calls == 1
    assert "legacy-1" not in cache.read_text(encoding="utf-8")


def test_complete_cache_is_reused_without_network(tmp_path, monkeypatch):
    cache = tmp_path / "instances.jsonl"
    rows = _candidates()
    monkeypatch.setattr(dataset, "_fetch_page", lambda _offset, _length: (rows, len(rows)))
    assert dataset.fetch_instances(cache_path=cache) == rows

    def unexpected_fetch(_offset: int, _length: int) -> tuple[list[dict[str, Any]], int]:
        raise AssertionError("complete cache should avoid network")

    monkeypatch.setattr(dataset, "_fetch_page", unexpected_fetch)
    assert dataset.fetch_instances(cache_path=cache) == rows


@pytest.mark.parametrize("separator", [" ", " ", "\x85"])
def test_cache_with_unicode_line_separators_is_reused_without_network(
    tmp_path, monkeypatch, separator
):
    """缓存用 ensure_ascii=False 写出；题面里的 U+2028 不是 JSONL 的行界。"""
    cache = tmp_path / "instances.jsonl"
    rows = [
        _row(
            "alpha-1",
            "org/alpha",
            "<15 min fix",
            problem_statement=f"first paragraph{separator}second paragraph",
        )
    ]
    monkeypatch.setattr(dataset, "_fetch_page", lambda _offset, _length: (rows, len(rows)))
    assert dataset.fetch_instances(cache_path=cache) == rows

    def unexpected_fetch(_offset: int, _length: int) -> tuple[list[dict[str, Any]], int]:
        raise AssertionError("complete cache should avoid network")

    monkeypatch.setattr(dataset, "_fetch_page", unexpected_fetch)
    assert dataset.fetch_instances(cache_path=cache) == rows


def test_undecodable_cache_is_refetched_instead_of_crashing(tmp_path, monkeypatch):
    cache = tmp_path / "instances.jsonl"
    rows = _candidates()
    monkeypatch.setattr(dataset, "_fetch_page", lambda _offset, _length: (rows, len(rows)))
    assert dataset.fetch_instances(cache_path=cache) == rows
    cache.write_bytes(b"\xff")

    assert dataset.fetch_instances(cache_path=cache) == rows
    assert cache.read_bytes() != b"\xff"


def test_selection_is_deterministic_stratified_and_prefix_stable():
    candidates = _candidates()
    selected = select_instances(candidates, len(candidates))
    shuffled = list(candidates)
    random.Random(20260806).shuffle(shuffled)

    assert [row["instance_id"] for row in selected] == [
        "alpha-1",
        "beta-1",
        "gamma-1",
        "alpha-2",
        "beta-2",
        "gamma-2",
        "alpha-3",
        "beta-3",
        "alpha-4",
    ]
    assert select_instances(shuffled, len(shuffled)) == selected
    for limit in range(len(candidates)):
        assert select_instances(candidates, limit) == selected[:limit]

    first_six = select_instances(candidates, 6)
    repo_counts = Counter(row["repo"] for row in first_six)
    assert repo_counts == {"org/alpha": 2, "org/beta": 2, "org/gamma": 2}


def test_difficulty_round_robin_and_unknown_fallback_are_stable():
    candidates = [
        _row("easy-a", "org/repo", "  <15   min fix "),
        _row("medium-a", "org/repo", "15 min - 1 hour"),
        _row("hard-a", "org/repo", "1-4 hours"),
        _row("long-a", "org/repo", ">4 hours"),
        _row("unknown-a", "org/repo", "new bucket"),
        _row("easy-b", "org/repo", "<15 min fix"),
    ]

    selected = select_instances(candidates, len(candidates))

    assert [normalize_difficulty(row["difficulty"]) for row in selected[:5]] == [
        "<15 min fix",
        "15 min - 1 hour",
        "1-4 hours",
        ">4 hours",
        "unknown",
    ]
    assert normalize_difficulty(None) == "unknown"
    assert normalize_difficulty("NEW BUCKET") == "unknown"


def test_selection_manifest_is_stable_and_contains_no_hidden_content():
    candidates = _candidates()
    selected = select_instances(candidates, 6)
    manifest = build_selection_manifest(candidates, selected, 6)
    shuffled = list(candidates)
    random.Random(41).shuffle(shuffled)
    repeated = build_selection_manifest(shuffled, select_instances(shuffled, 6), 6)

    assert repeated == manifest
    assert manifest["repo_counts"] == {"org/alpha": 2, "org/beta": 2, "org/gamma": 2}
    assert manifest["difficulty_counts"] == {
        "1-4 hours": 1,
        "15 min - 1 hour": 2,
        "<15 min fix": 2,
        ">4 hours": 1,
    }
    serialized = json.dumps(manifest, ensure_ascii=False)
    assert "problem_statement" not in serialized
    assert "FAIL_TO_PASS" not in serialized
    assert "PASS_TO_PASS" not in serialized
    assert "secret issue" not in serialized
    assert "secret::f2p" not in serialized


def test_selection_only_writes_manifest_without_docker_or_prediction(tmp_path, monkeypatch):
    output = tmp_path / "preds.jsonl"
    monkeypatch.setattr(run, "fetch_instances", lambda **_kwargs: _candidates())
    monkeypatch.setattr(
        run, "docker_preflight", lambda: pytest.fail("selection-only must not inspect Docker")
    )
    monkeypatch.setattr(
        run, "build_client", lambda *_args: pytest.fail("selection-only must not build a client")
    )
    monkeypatch.setattr(
        run, "predict_one", lambda *_args, **_kwargs: pytest.fail("selection-only must not predict")
    )

    exit_code = run.main(
        [
            "--limit",
            "6",
            "--output",
            str(output),
            "--selection-only",
            "--cache",
            str(tmp_path / "x"),
        ]
    )

    assert exit_code == 0
    assert not output.exists()
    manifest = json.loads((tmp_path / "preds.selection.json").read_text(encoding="utf-8"))
    assert manifest["selected_count"] == 6
    assert len(manifest["repo_counts"]) == 3


def test_docker_preflight_failure_does_not_replace_existing_output_contract(
    tmp_path, monkeypatch, capsys
):
    # 不预先创建 output：否则运行会停在更早的防覆盖守卫上，根本走不到 docker 预检。
    output = tmp_path / "preds.jsonl"
    manifest_path = tmp_path / "preds.selection.json"
    manifest_path.write_text('{"selection_signature":"old"}\n', encoding="utf-8")
    monkeypatch.setattr(run, "fetch_instances", lambda **_kwargs: _candidates())
    monkeypatch.setattr(run, "docker_preflight", lambda: "daemon unavailable")
    monkeypatch.setattr(
        run, "predict_one", lambda *_args, **_kwargs: pytest.fail("must stop at the preflight")
    )

    assert run.main(["--limit", "6", "--output", str(output)]) == 2
    assert "docker 不可用：daemon unavailable" in capsys.readouterr().err
    assert not output.exists()
    assert manifest_path.read_text(encoding="utf-8") == '{"selection_signature":"old"}\n'


def test_client_preflight_failure_stops_before_manifest_and_prediction(
    tmp_path, monkeypatch, capsys
):
    """缺 API key 必须在拉任何镜像之前失败，而不是每题物化完工作区再各记一条 harness_error。"""
    output = tmp_path / "preds.jsonl"

    def missing_key(*_args):
        raise RuntimeError("环境变量 DEEPSEEK_API_KEY 未设置；预测阶段需要真实 API key。")

    monkeypatch.setattr(run, "fetch_instances", lambda **_kwargs: _candidates())
    monkeypatch.setattr(run, "docker_preflight", lambda: "")
    monkeypatch.setattr(run, "build_client", missing_key)
    monkeypatch.setattr(
        run, "predict_one", lambda *_args, **_kwargs: pytest.fail("must stop at the preflight")
    )

    assert run.main(["--limit", "3", "--output", str(output)]) == 2
    assert "DEEPSEEK_API_KEY" in capsys.readouterr().err
    assert not output.exists()
    assert not (tmp_path / "preds.selection.json").exists()


@pytest.mark.parametrize("value", ["0", "-5"])
def test_non_positive_max_steps_is_rejected_before_any_work(tmp_path, monkeypatch, value):
    monkeypatch.setattr(
        run, "fetch_instances", lambda **_kwargs: pytest.fail("must validate arguments first")
    )

    with pytest.raises(SystemExit) as excinfo:
        run.main(["--output", str(tmp_path / "preds.jsonl"), "--max-steps", value])

    assert excinfo.value.code == 2


@pytest.mark.parametrize("mode", ["missing", "mismatch", "outside", "duplicate", "bad_utf8"])
def test_resume_rejects_incompatible_selection_before_docker(mode, tmp_path, monkeypatch, capsys):
    output = tmp_path / "preds.jsonl"
    manifest_path = tmp_path / "preds.selection.json"
    candidates = _candidates()
    selected = select_instances(candidates, 3)
    manifest = build_selection_manifest(candidates, selected, 3)
    records = [{"instance_id": selected[0]["instance_id"], "dm_status": "success"}]
    if mode == "mismatch":
        manifest["selection_signature"] = "different"
    elif mode == "outside":
        records = [{"instance_id": "other-repo-1", "dm_status": "success"}]
    elif mode == "duplicate":
        records = records * 2
    output.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    original_output = output.read_text(encoding="utf-8")
    if mode == "bad_utf8":
        manifest_path.write_bytes(b"\xff")
    elif mode != "missing":
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(run, "fetch_instances", lambda **_kwargs: candidates)
    monkeypatch.setattr(run, "docker_preflight", lambda: pytest.fail("guard must run first"))

    assert run.main(["--limit", "3", "--output", str(output), "--resume"]) == 2
    assert output.read_text(encoding="utf-8") == original_output
    assert "无法续跑" in capsys.readouterr().err


@pytest.mark.parametrize("failed_index", [0, 1])
def test_resume_keeps_completed_records_and_retries_harness_error(
    tmp_path, monkeypatch, failed_index
):
    output = tmp_path / "preds.jsonl"
    candidates = _candidates()
    selected = select_instances(candidates, 2)
    manifest = build_selection_manifest(candidates, selected, 2)
    (tmp_path / "preds.selection.json").write_text(json.dumps(manifest), encoding="utf-8")
    original = "".join(
        json.dumps(
            {
                "instance_id": row["instance_id"],
                "dm_status": "harness_error" if index == failed_index else "success",
            }
        )
        + "\n"
        for index, row in enumerate(selected)
    ).encode("utf-8")
    output.write_bytes(original)
    predicted: list[str] = []

    def predict_one(instance: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        predicted.append(instance["instance_id"])
        return {
            "instance_id": instance["instance_id"],
            "dm_status": "success",
            "dm_patch_chars": 10,
            "dm_steps": 1,
            "dm_duration_seconds": 0.1,
        }

    monkeypatch.setattr(run, "fetch_instances", lambda **_kwargs: candidates)
    monkeypatch.setattr(run, "docker_preflight", lambda: "")
    monkeypatch.setattr(run, "predict_one", predict_one)
    monkeypatch.setattr(run, "build_client", lambda *_args: object())

    assert run.main(["--limit", "2", "--output", str(output), "--resume"]) == 0
    assert predicted == [selected[failed_index]["instance_id"]]
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [record["instance_id"] for record in records] == [
        selected[0]["instance_id"],
        selected[1]["instance_id"],
    ]
    assert all(record["dm_status"] == "success" for record in records)
    backups = list(tmp_path.glob(".preds.jsonl.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original


def test_prediction_output_is_not_overwritten_without_resume(tmp_path, monkeypatch):
    output = tmp_path / "preds.jsonl"
    original = b'{"instance_id":"old"}\n'
    output.write_bytes(original)
    monkeypatch.setattr(
        run, "fetch_instances", lambda **kwargs: pytest.fail("guard must run first")
    )

    assert run.main(["--output", str(output)]) == 2
    assert output.read_bytes() == original


def test_failed_resume_rewrite_preserves_original_predictions(tmp_path, monkeypatch):
    candidates = _candidates()
    selected = select_instances(candidates, 1)
    manifest = build_selection_manifest(candidates, selected, 1)
    output = tmp_path / "preds.jsonl"
    (tmp_path / "preds.selection.json").write_text(json.dumps(manifest), encoding="utf-8")
    original = (
        json.dumps(
            {"instance_id": selected[0]["instance_id"], "dm_status": "harness_error"}
        ).encode("utf-8")
        + b"\n"
    )
    output.write_bytes(original)
    monkeypatch.setattr(run, "fetch_instances", lambda **kwargs: candidates)
    monkeypatch.setattr(run, "docker_preflight", lambda: "")
    monkeypatch.setattr(run, "predict_one", lambda *args, **kwargs: pytest.fail("rewrite failed"))
    monkeypatch.setattr(run, "build_client", lambda *_args: object())

    def fail_replace(self, target):
        raise OSError("disk unavailable")

    monkeypatch.setattr(type(output), "replace", fail_replace)

    assert run.main(["--limit", "1", "--output", str(output), "--resume"]) == 2
    assert output.read_bytes() == original
    assert [path.read_bytes() for path in tmp_path.glob(".preds.jsonl.*.bak")] == [original]
    assert not list(tmp_path.glob(".preds.jsonl.*.tmp"))


def test_completed_resume_does_not_rewrite_predictions(tmp_path, monkeypatch):
    candidates = _candidates()
    selected = select_instances(candidates, 1)
    manifest = build_selection_manifest(candidates, selected, 1)
    output = tmp_path / "preds.jsonl"
    (tmp_path / "preds.selection.json").write_text(json.dumps(manifest), encoding="utf-8")
    original = (
        json.dumps(
            {"instance_id": selected[0]["instance_id"], "dm_status": "success"},
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\r\n"
    )
    output.write_bytes(original)
    monkeypatch.setattr(run, "fetch_instances", lambda **kwargs: candidates)
    monkeypatch.setattr(run, "docker_preflight", lambda: "")
    monkeypatch.setattr(
        run, "predict_one", lambda *args, **kwargs: pytest.fail("already completed")
    )
    monkeypatch.setattr(run, "build_client", lambda *_args: object())

    assert run.main(["--limit", "1", "--output", str(output), "--resume"]) == 0
    assert output.read_bytes() == original
    assert not list(tmp_path.glob("*.bak"))


def test_completed_legacy_resume_restores_manifest_order_with_backup(tmp_path, monkeypatch):
    candidates = _candidates()
    selected = select_instances(candidates, 2)
    manifest = build_selection_manifest(candidates, selected, 2)
    output = tmp_path / "preds.jsonl"
    (tmp_path / "preds.selection.json").write_text(json.dumps(manifest), encoding="utf-8")
    original = "".join(
        json.dumps({"instance_id": row["instance_id"], "dm_status": "success"}) + "\n"
        for row in reversed(selected)
    ).encode("utf-8")
    output.write_bytes(original)
    monkeypatch.setattr(run, "fetch_instances", lambda **kwargs: candidates)
    monkeypatch.setattr(run, "docker_preflight", lambda: "")
    monkeypatch.setattr(
        run, "predict_one", lambda *args, **kwargs: pytest.fail("already completed")
    )
    monkeypatch.setattr(run, "build_client", lambda *_args: object())

    assert run.main(["--limit", "2", "--output", str(output), "--resume"]) == 0
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [record["instance_id"] for record in records] == manifest["instance_ids"]
    assert [path.read_bytes() for path in tmp_path.glob(".preds.jsonl.*.bak")] == [original]
