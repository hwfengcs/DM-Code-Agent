"""Tests for the SWE-bench Lite suite.

These tests deliberately avoid network and the optional ``datasets`` library.
They cover loader, fixed-subset sampling, analyzer, model serialization, and
the lazy ``__getattr__`` import boundary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dm_agent.benchmarks.swebench_lite.analyzer import (
    categorize_failure,
    render_full_analysis,
    summarize_failure_modes,
)
from dm_agent.benchmarks.swebench_lite.loader import (
    fixed_subset_50,
    load_instances,
    load_instances_from_jsonl,
    snapshot_to_jsonl,
    subset_signature,
)
from dm_agent.benchmarks.swebench_lite.models import (
    FailureCategory,
    SWEBenchInstance,
    SWEBenchResult,
    SWEBenchVerification,
)


def _instance(
    instance_id: str,
    *,
    repo: str = "octo/example",
    base_commit: str = "0" * 40,
    fail_to_pass=None,
    pass_to_pass=None,
) -> SWEBenchInstance:
    return SWEBenchInstance(
        instance_id=instance_id,
        repo=repo,
        version="1.0",
        base_commit=base_commit,
        environment_setup_commit=base_commit,
        problem_statement="Add a missing comma to the greeter.",
        hints_text="",
        created_at="2024-01-01T00:00:00Z",
        patch="",
        test_patch="",
        fail_to_pass=list(fail_to_pass or ["tests/test_x.py::test_a"]),
        pass_to_pass=list(pass_to_pass or ["tests/test_x.py::test_b"]),
    )


@pytest.fixture
def sample_jsonl(tmp_path: Path) -> Path:
    instances = [
        _instance("octo__example-1"),
        _instance("octo__example-2", repo="octo/other"),
    ]
    path = tmp_path / "snapshot.jsonl"
    snapshot_to_jsonl(instances, path)
    return path


def test_snapshot_round_trip(sample_jsonl: Path) -> None:
    loaded = load_instances_from_jsonl(sample_jsonl)
    assert [inst.instance_id for inst in loaded] == [
        "octo__example-1",
        "octo__example-2",
    ]
    assert loaded[0].repo == "octo/example"
    assert loaded[1].repo == "octo/other"


def test_load_instances_uses_local_snapshot(sample_jsonl: Path) -> None:
    loaded = load_instances(snapshot_path=sample_jsonl)
    assert len(loaded) == 2
    assert loaded[0].fail_to_pass == ["tests/test_x.py::test_a"]


def test_load_instances_filters_by_id(sample_jsonl: Path) -> None:
    loaded = load_instances(
        snapshot_path=sample_jsonl,
        instance_ids=["octo__example-2"],
    )
    assert len(loaded) == 1
    assert loaded[0].instance_id == "octo__example-2"


def test_load_instances_limit(sample_jsonl: Path) -> None:
    loaded = load_instances(snapshot_path=sample_jsonl, limit=1)
    assert len(loaded) == 1


def test_fixed_subset_50_is_deterministic_and_repo_balanced() -> None:
    pool = []
    for repo_index in range(20):
        for instance_index in range(10):
            pool.append(
                _instance(
                    instance_id=f"repo{repo_index:02d}__case-{instance_index}",
                    repo=f"acme/repo{repo_index:02d}",
                )
            )

    first = fixed_subset_50(instances=pool, size=50)
    second = fixed_subset_50(instances=pool, size=50)
    assert [i.instance_id for i in first] == [i.instance_id for i in second]
    assert len(first) == 50

    # Repo cap should keep no single repo above max_per_repo.
    by_repo: dict[str, int] = {}
    for inst in first:
        by_repo[inst.repo] = by_repo.get(inst.repo, 0) + 1
    assert max(by_repo.values()) <= 5


def test_subset_signature_is_stable_and_short() -> None:
    pool = [_instance(f"x__case-{i}", repo=f"acme/r{i % 3}") for i in range(30)]
    subset_a = fixed_subset_50(instances=pool, size=10)
    subset_b = fixed_subset_50(instances=pool, size=10)
    sig_a = subset_signature(subset_a)
    sig_b = subset_signature(subset_b)
    assert sig_a == sig_b
    assert len(sig_a) == 12


def _result(
    *,
    instance_id: str = "octo__example-1",
    success: bool = False,
    prediction: str = "diff --git a/x b/x\n",
    verification: SWEBenchVerification | None = None,
    metadata: dict | None = None,
    failure_reason: str = "",
) -> SWEBenchResult:
    instance = _instance(instance_id)
    if verification is None:
        verification = SWEBenchVerification(
            patch_applied=True,
            fail_to_pass_pass=0,
            fail_to_pass_total=len(instance.fail_to_pass),
            pass_to_pass_pass=len(instance.pass_to_pass),
            pass_to_pass_total=len(instance.pass_to_pass),
        )
    return SWEBenchResult(
        instance_id=instance.instance_id,
        repo=instance.repo,
        success=success,
        failure_reason=failure_reason,
        final_answer="",
        actions=[],
        steps_count=0,
        tool_calls=0,
        duration_seconds=0.0,
        prompt_chars=0,
        completion_chars=0,
        estimated_tokens=0,
        request_count=0,
        metadata=metadata or {},
        verification=verification,
        prediction=prediction,
    )


def test_categorize_failure_no_patch_produced() -> None:
    result = _result(
        prediction="",
        verification=SWEBenchVerification(
            patch_applied=False,
            fail_to_pass_pass=0,
            fail_to_pass_total=1,
            pass_to_pass_pass=0,
            pass_to_pass_total=1,
            error="empty_prediction",
        ),
    )
    assert categorize_failure(result) is FailureCategory.PATCH_NOT_PRODUCED


def test_categorize_failure_patch_apply_failed() -> None:
    result = _result(
        prediction="invalid diff",
        verification=SWEBenchVerification(
            patch_applied=False,
            fail_to_pass_pass=0,
            fail_to_pass_total=1,
            pass_to_pass_pass=0,
            pass_to_pass_total=1,
            error="patch_apply_failed",
        ),
    )
    assert categorize_failure(result) is FailureCategory.PATCH_APPLY_FAILED


def test_categorize_failure_hidden_test_fail() -> None:
    result = _result(
        verification=SWEBenchVerification(
            patch_applied=True,
            fail_to_pass_pass=0,
            fail_to_pass_total=2,
            pass_to_pass_pass=2,
            pass_to_pass_total=2,
        )
    )
    assert categorize_failure(result) is FailureCategory.HIDDEN_TEST_FAIL


def test_categorize_failure_regression_takes_priority_over_hidden_test() -> None:
    result = _result(
        verification=SWEBenchVerification(
            patch_applied=True,
            fail_to_pass_pass=2,
            fail_to_pass_total=2,
            pass_to_pass_pass=1,
            pass_to_pass_total=2,
        )
    )
    assert categorize_failure(result) is FailureCategory.REGRESSION


def test_categorize_failure_max_steps_metadata() -> None:
    result = _result(
        metadata={"status": "max_steps"},
        verification=SWEBenchVerification(
            patch_applied=False,
            fail_to_pass_pass=0,
            fail_to_pass_total=1,
            pass_to_pass_pass=0,
            pass_to_pass_total=1,
        ),
    )
    assert categorize_failure(result) is FailureCategory.MAX_STEPS


def test_summarize_failure_modes_distribution() -> None:
    successes = [
        _result(success=True),
        _result(success=True),
    ]
    failures = [
        _result(
            prediction="",
            verification=SWEBenchVerification(
                patch_applied=False,
                fail_to_pass_pass=0,
                fail_to_pass_total=1,
                pass_to_pass_pass=0,
                pass_to_pass_total=1,
                error="empty_prediction",
            ),
        ),
        _result(
            verification=SWEBenchVerification(
                patch_applied=True,
                fail_to_pass_pass=0,
                fail_to_pass_total=1,
                pass_to_pass_pass=1,
                pass_to_pass_total=1,
            )
        ),
    ]
    summary = summarize_failure_modes(successes + failures)
    assert summary["total"] == 4
    assert summary["successes"] == 2
    assert summary["failures"] == 2

    rate_by_cat = {entry["category"]: entry["count"] for entry in summary["per_category"]}
    assert rate_by_cat["patch_not_produced"] == 1
    assert rate_by_cat["hidden_test_fail"] == 1


def test_render_full_analysis_emits_table() -> None:
    failure = _result(
        verification=SWEBenchVerification(
            patch_applied=True,
            fail_to_pass_pass=0,
            fail_to_pass_total=1,
            pass_to_pass_pass=1,
            pass_to_pass_total=1,
        )
    )
    rendered = render_full_analysis([failure])
    assert "Failure modes" in rendered
    assert "hidden_test_fail" in rendered


def test_swebench_result_round_trips_from_report_dict() -> None:
    result = _result(
        instance_id="octo__example-9",
        metadata={"status": "success"},
        verification=SWEBenchVerification(
            patch_applied=True,
            fail_to_pass_pass=1,
            fail_to_pass_total=1,
            pass_to_pass_pass=1,
            pass_to_pass_total=1,
        ),
    )

    restored = SWEBenchResult.from_dict(result.to_dict())

    assert restored.instance_id == "octo__example-9"
    assert restored.metadata == {"status": "success"}
    assert restored.verification.resolved is True


def test_run_swebench_lite_resume_skips_completed_and_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from dm_agent.benchmarks.swebench_lite import runner as runner_module
    from dm_agent.benchmarks.swebench_lite.models import SWEBenchRunConfig

    first = _instance("octo__example-1")
    second = _instance("octo__example-2")
    resumed = _result(instance_id=first.instance_id, failure_reason="old_result")
    fresh = _result(
        instance_id=second.instance_id,
        success=True,
        verification=SWEBenchVerification(
            patch_applied=True,
            fail_to_pass_pass=1,
            fail_to_pass_total=1,
            pass_to_pass_pass=1,
            pass_to_pass_total=1,
        ),
    )
    calls: list[str] = []

    def fake_run_single_instance(*args, **kwargs):
        instance = args[0]
        calls.append(instance.instance_id)
        return fresh

    monkeypatch.setattr(runner_module, "_run_single_instance", fake_run_single_instance)

    checkpoints: list[dict] = []
    report = runner_module.run_swebench_lite(
        [first, second],
        config=SWEBenchRunConfig(workspace_root=str(tmp_path)),
        resume_results=[resumed],
        progress_callback=checkpoints.append,
    )

    assert calls == [second.instance_id]
    assert [r["instance_id"] for r in report["results"]] == [
        first.instance_id,
        second.instance_id,
    ]
    assert report["summary"]["total"] == 2
    assert report["summary"]["resolved"] == 1
    assert report["resume"]["reused_results"] == 1
    assert len(checkpoints) == 1
    assert checkpoints[0]["summary"]["total"] == 2


def test_swebench_pytest_output_tolerates_invalid_utf8(tmp_path: Path) -> None:
    from dm_agent.benchmarks.swebench_lite.verifier import _run_pytest_node

    test_file = tmp_path / "test_bad_output.py"
    test_file.write_text(
        "import os\n\n"
        "def test_bad_output():\n"
        "    os.write(1, b'bad-byte: \\x99\\n')\n"
        "    assert False\n",
        encoding="utf-8",
    )

    outcome = _run_pytest_node(str(test_file) + "::test_bad_output", tmp_path, timeout=10)

    assert outcome.passed is False
    assert outcome.returncode != 0
    assert isinstance(outcome.stdout_tail, str)
    assert "test_bad_output" in outcome.stdout_tail


def test_lazy_attribute_access_does_not_require_datasets() -> None:
    """Accessing the package's non-loader exports should not import datasets."""
    import dm_agent.benchmarks.swebench_lite as pkg

    fn = pkg.categorize_failure  # triggers __getattr__
    assert callable(fn)

    runner = pkg.run_swebench_lite
    assert callable(runner)
