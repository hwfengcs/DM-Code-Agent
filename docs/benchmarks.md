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

Opt-in adaptive replanning and local token accounting:

```bash
dm-agent-bench --suite maintenance \
  --provider deepseek \
  --enable-adaptive-replanning \
  --max-replans 3 \
  --cost-per-1k-tokens 0.00027 \
  --output bench_reports/maintenance.json \
  --markdown bench_reports/maintenance.md
```

Generate an offline economics table from existing JSON reports:

```bash
dm-agent-economics bench_reports/maintenance.json \
  --label maintenance-deepseek \
  --output-json bench_reports/economics.json \
  --output-md bench_reports/economics.md
```

`dm-agent-economics` never runs a model, downloads a dataset, or queries live pricing. Prices are
explicit inputs for local accounting.

Default-off v2 plumbing for coding/maintenance benchmark experiments:

```bash
dm-agent-bench --suite maintenance \
  --enable-rag \
  --rag-top-k 5 \
  --enable-critic \
  --self-consistency-runs 3 \
  --self-consistency-strategy test_pass
```

RAG builds a local BM25 index for each candidate workspace. Critic review uses the same configured
LLM client as the main run unless future code supplies a separate client. Self-consistency creates
fresh workspaces per candidate and then selects by majority vote, critic score, or test pass. These
features are disabled by default and are not used by CI live runs.

SWE-bench Lite self-consistency is intentionally blocked while real SWE-bench evaluation is frozen.

## Maintenance Suite

The maintenance suite currently includes:

- `config_precedence`: config precedence and type coercion.
- `patch_summary_name_status`: git `diff --name-status` parsing for run reports.
- `retry_regression_tests`: retry policy fix with required regression-test changes.
- `safe_workspace_join`: path traversal protection for workspace file access.
- `cross_file_user_contract`: cross-file API contract repair for a serializer/model pair.
- `cli_config_docs_contract`: multi-file CLI/docs/test consistency repair for configuration
  documentation.

These tasks are intentionally closer to repository upkeep than puzzle-style algorithms. They
include hidden tests, edge cases, and changed-file constraints.

## Scoring

A run is successful only if:

1. The agent reports successful completion.
2. Hidden tests pass.
3. The task's changed-file constraints are satisfied.

The report includes:

- `overall_pass_rate`
- `overall_pass_rate_ci_95`
- `overall_hidden_test_pass_rate`
- `overall_hidden_test_pass_rate_ci_95`
- `overall_agent_completion_rate`
- `overall_agent_completion_rate_ci_95`
- average steps
- average tool calls
- average changed files
- estimated tokens
- estimated cost and cost per success when `--cost-per-1k-tokens` is provided
- provider request count
- per-run changed files
- optional per-run trace paths
- hidden test stdout/stderr tail
- agent metadata such as replan, parse repair, and tool error counts
- adaptive replanning metadata when enabled: signal kind, selected strategy, skipped replans,
  and replan budget exhaustion
- RAG / critic / self-consistency configuration metadata when those default-off switches are used
- self-consistency uncertainty metadata when multiple candidates are run: vote distribution,
  selected support, support fraction, tie detection, margin to runner-up, and confidence label

Pass-rate confidence intervals use Wilson 95% intervals. They are computed from the runs already in
the report and do not increase the default repeat count.

## Changed-File Constraints

`BenchmarkTask` supports:

- `allowed_changed_files`: files the agent may change.
- `required_changed_files`: files the agent must change.

This makes the benchmark more practical. A task can require the agent to add regression tests,
or fail a run that edits unrelated files to game the score.

## Design Direction

Future benchmark work should add:

- more multi-file refactors with behavior-preserving hidden tests
- documentation/CLI consistency tasks
- CI and packaging repair tasks
- trace completeness checks
- richer repeated-sample variance summaries beyond binomial confidence intervals
- cross-model comparison tables
- cost-per-success economics across existing reports
