# 15 — Trace directory analysis aggregation

## TL;DR

`dm-agent-trace analyze-dir` analyzes every trace in a directory and reports aggregate trace-health,
verification-gap, and failure-stage counts. It is offline and read-only, just like single-trace
analysis.

## Context

Single-run trace analysis is useful for debugging one failure. Benchmark runs produce a directory of
traces, so reviewers need aggregate signals:

- how many traces are `good`, `warning`, or `risky`;
- how many successful runs skipped local verification;
- which final failure stages dominate the suite.

Before this change, users had to script that aggregation themselves.

## What Changed

- `dm-agent-trace analyze-dir TRACE_DIR`
- `dm-agent-trace analyze-dir TRACE_DIR --json`
- `--pattern` for non-default trace file names
- `analyze_trace_directory(...)` for programmatic use

The summary includes:

- `total_files`
- `analyzed_traces`
- `error_count`
- `verification_gap_count`
- `trace_health_counts`
- `primary_failure_stage_counts`
- `final_failure_stage_counts`

## Keyless Checks

```bash
python -m pytest tests/test_tracing.py
python -m ruff check dm_agent/tracing/cli.py dm_agent/tracing/__init__.py tests/test_tracing.py
python -m black --check dm_agent/tracing/cli.py dm_agent/tracing/__init__.py tests/test_tracing.py
```

## Open Questions / Next Bets

- Link directory Markdown reports from benchmark Markdown output.
- Link directory analysis summaries from benchmark Markdown reports.
- Add trace-diff aggregation for baseline/candidate trace pairs.
