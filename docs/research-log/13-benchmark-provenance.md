# 13 — Benchmark manifest provenance and suite signatures

## TL;DR

Benchmark JSON reports now include a `manifest` block with task ids, per-task fingerprints, variant
names, and a suite signature. Task fingerprints hash the full task contract, including hidden-test
content and changed-file constraints, without exposing hidden-test text.

This makes benchmark reports more reproducible: if a task, hidden test, prompt, command, or file
constraint changes, the fingerprint changes.

## Context

Pass rates and confidence intervals are only meaningful when the task suite is stable. Before this
change, reports included public task metadata, but they did not include a compact signature of the
hidden contract. That made it harder to compare two local reports and know whether a score changed
because the agent improved or because the benchmark changed.

## What Changed

- `benchmark_task_fingerprint(task)` hashes:
  - task id/name/prompt;
  - setup file contents;
  - hidden file contents;
  - visible and hidden test commands;
  - max steps and tags;
  - allowed and required changed-file constraints.
- `build_benchmark_manifest(...)` records:
  - suite name;
  - sorted task ids;
  - task fingerprints;
  - variant names;
  - suite signature.
- `run_benchmark_suite(...)` includes the manifest in every generic coding/maintenance report.

## Privacy Boundary

The report does not include hidden-test source. It includes only the hash. This keeps hidden tests
hidden while still making drift visible.

## Keyless Checks

```bash
python -m pytest tests/test_coding_benchmarks.py
python -m ruff check dm_agent/benchmarks/runner.py tests/test_coding_benchmarks.py
python -m black --check dm_agent/benchmarks/runner.py tests/test_coding_benchmarks.py
```

## Open Questions / Next Bets

- Add trace completeness fields to benchmark reports when `--trace-dir` is enabled.
- Include benchmark runner version and Python version in the manifest block.
- Add a small CLI to compare two benchmark manifests before comparing scores.
