# Benchmarks

DM-Code-Agent has two benchmark suites:

- `coding`: compact hidden-test coding tasks.
- `maintenance`: repository-maintenance tasks that mimic real fixes more closely.

Both suites create a temporary workspace, let the agent inspect and edit files, inject hidden
tests after the agent finishes, and score the run by executable behavior.

## Commands

List coding tasks:

```bash
dm-agent-bench --list
```

List maintenance tasks:

```bash
dm-agent-bench --suite maintenance --list
```

Run one task:

```bash
dm-agent-bench --suite maintenance --provider deepseek --task config_precedence
```

Write reports:

```bash
dm-agent-bench --suite maintenance \
  --provider deepseek \
  --output bench_reports/maintenance.json \
  --markdown bench_reports/maintenance.md \
  --trace-dir bench_reports/traces
```

## Maintenance Suite

The maintenance suite currently includes:

- `config_precedence`: config precedence and type coercion.
- `patch_summary_name_status`: git `diff --name-status` parsing for run reports.
- `retry_regression_tests`: retry policy fix with required regression-test changes.
- `safe_workspace_join`: path traversal protection for workspace file access.
- `cross_file_user_contract`: cross-file API contract repair for a serializer/model pair.

These tasks are intentionally closer to repository upkeep than puzzle-style algorithms. They
include hidden tests, edge cases, and changed-file constraints.

## Scoring

A run is successful only if:

1. The agent reports successful completion.
2. Hidden tests pass.
3. The task's changed-file constraints are satisfied.

The report includes:

- `overall_pass_rate`
- `overall_hidden_test_pass_rate`
- `overall_agent_completion_rate`
- average steps
- average tool calls
- average changed files
- estimated tokens
- provider request count
- per-run changed files
- optional per-run trace paths
- hidden test stdout/stderr tail
- agent metadata such as replan, parse repair, and tool error counts

## Changed-File Constraints

`BenchmarkTask` supports:

- `allowed_changed_files`: files the agent may change.
- `required_changed_files`: files the agent must change.

This makes the benchmark more practical. A task can require the agent to add regression tests,
or fail a run that edits unrelated files to game the score.

## Design Direction

Future benchmark work should add:

- multi-file refactors with behavior-preserving hidden tests
- documentation/CLI consistency tasks
- CI and packaging repair tasks
- trace completeness checks
- repeated-sample confidence intervals
- cross-model comparison tables
