# 14 — Benchmark trace-analysis metadata

## TL;DR

Coding and maintenance benchmark reports now attach compact `trace_analysis` metadata for each run
when `--trace-dir` is enabled. The analysis includes primary/final failure stage, recovery,
verification gap, and trace-health grade.

This is advisory metadata only. Hidden tests and changed-file constraints remain the scoring source
of truth.

## Context

Entry 08 added `dm-agent-trace analyze` for single traces. Entry 13 added benchmark manifest
provenance. The natural next step is to let benchmark reports point directly at trace health without
requiring a manual second CLI pass for every run.

The integration is intentionally conditional: no `--trace-dir`, no trace-analysis metadata.

## What Changed

- `load_trace_analysis_for_report(trace_path)` loads and compacts analyzer output.
- `_run_benchmark_task_in_workspace(...)` attaches `metadata.trace_analysis` when a trace file was
  written.
- If the trace cannot be loaded, `metadata.trace_analysis_error` records the local error.
- Tests write a tiny trace with `TraceWriter` and verify keyless analysis loading.

## Compact Fields

The report stores:

- `primary_failure_stage`
- `final_failure_stage`
- `signals`
- `recovery`
- `verification`
- `trace_health`

It omits full task text and full trace events because the trace file path is already present in
metadata.

## Why It Is Advisory

Trace analysis can flag a successful run that did not execute `run_tests`, but some tasks may be
validly completed by static inspection or docs-only changes. The field is meant to help reviewers
triage, not fail a benchmark run.

## Keyless Checks

```bash
python -m pytest tests/test_coding_benchmarks.py
python -m ruff check dm_agent/benchmarks/runner.py tests/test_coding_benchmarks.py
python -m black --check dm_agent/benchmarks/runner.py tests/test_coding_benchmarks.py
```

## Open Questions / Next Bets

- Aggregate `trace_health` counts in the top-level benchmark summary.
- Add a `dm-agent-trace analyze-dir` command for trace directories.
- Link trace analysis to trace diff when baseline/candidate trace pairs are available.
