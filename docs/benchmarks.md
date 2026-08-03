# Benchmarks

**This is the project's scoreboard.** It is the only place a real number about agent capability
comes from, so read the caveats before quoting it.

Three suites:

- `coding` (6 tasks): compact hidden-test coding tasks.
- `maintenance` (7 tasks): repository-maintenance tasks that mimic real fixes more closely.
- `all` (13 tasks): both of the above in one run — **use this when you want one score.**

Every suite creates a temporary workspace, lets the agent inspect and edit files, injects hidden
tests after the agent finishes, and scores the run by executable behavior. No Docker, no
HuggingFace download — but a real API key is required, because the point is to measure a real model.

## How to read the score

The headline number is `summary.overall_pass_rate`. The archived baseline
(`bench_reports/baseline-20260803.json`, DeepSeek `deepseek-chat`, suite `all`, 2026-08-03):

| Metric | Value |
| --- | --- |
| `overall_pass_rate` | **0.385** (5/13) |
| 95% CI (Wilson) | [0.177, 0.645] |
| `hidden_test_pass_rate` | 0.769 |
| `agent_completion_rate` | 0.615 |
| Total tokens | 750,672 |
| Wall clock | 7.1 min |

Read the gap between those rates, not just the first line. Hidden tests pass on **77%** of tasks
while only **38%** count as a pass — the difference is process discipline, not coding ability:
three tasks edited files the prompt forbade (all three went for the test file), four ran out of
steps, one produced unparseable output.

A concrete demonstration of why the noise floor matters: an earlier run of the same 6 coding
tasks with the same model scored 3/6, this baseline scores 4/6. **Same model, same tasks, one
task of difference.** That is the ±7.7 points talking, not a change in capability.

**At 13 tasks, one flipped task is ±7.7 percentage points.** That is the single most important
thing to know about this number:

- It is good for *"did my change help?"* — run before, run after, compare.
- It is **not** good for comparing against other projects, and a swing of one or two tasks is
  not evidence of anything. `dm-agent-score-diff` says so out loud rather than letting you
  read a 1-task flip as an improvement.
- `pass_rate_ci_95` (Wilson interval) is in every report. At this sample size it is wide. That
  is honest, not a defect.

## Comparing two runs

```bash
dm-agent-bench --suite all --provider deepseek --output bench_reports/before.json
# ... change a strategy ...
dm-agent-bench --suite all --provider deepseek --output bench_reports/after.json

dm-agent-score-diff bench_reports/before.json bench_reports/after.json
```

Output gives the pass-rate delta, **which specific tasks flipped in each direction**, and the
token/cost change. Per-task flips matter more than the total: "总分 +7.7%" tells you almost
nothing, "`ttl_cache_lru` started passing and `safe_workspace_join` started failing" tells you
where to look next.

Regressions are always listed separately, **even when the total went up** — that is the failure
mode a single aggregate number hides. Exit code is `1` when any task regressed, so it can gate
a script. If the two reports have different task sets, the tool refuses to compare
(`exit 2`) instead of printing a meaningless delta.

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

Each JSON report includes a `manifest` block with task fingerprints and a suite signature. Task
fingerprints include hidden-test content and changed-file constraints, so reports can detect suite
drift without exposing hidden tests.

When `--trace-dir` is enabled, each run metadata also includes compact `trace_analysis` fields:
primary/final failure stage, recovery, verification gap, and trace-health grade. This is advisory
debugging metadata and does not affect hidden-test scoring.

Opt-in adaptive replanning and local token accounting:

```bash
dm-agent-bench --suite maintenance \
  --provider deepseek \
  --enable-adaptive-replanning \
  --enable-repeated-failure-policy-experiment \
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
explicit inputs for local accounting. When source benchmark reports include pass-rate confidence
intervals, the economics Markdown carries those intervals into the pass-rate column. When multiple
input reports carry different `manifest.suite_signature` values, the economics summary and Markdown
emit a warning because cost/pass-rate rankings may not be comparable.

Compare two benchmark manifests before comparing scores:

```bash
dm-agent-manifest-diff bench_reports/baseline.json bench_reports/experiment.json
```

The manifest diff is offline-only. It exits with `0` when suite signatures, task fingerprints, and
variant names match; it exits with `1` when reports are from different task contracts.

Default-off plumbing for coding/maintenance benchmark experiments:

```bash
dm-agent-bench --suite maintenance --enable-adaptive-replanning --max-replans 3
```

> v2.1 removed the Critic and self-consistency benchmark switches along with the
> SWE-bench Lite suite. See [devlog 33](research-log/33-scope-reduction.md).

## Maintenance Suite

The maintenance suite currently includes:

- `config_precedence`: config precedence and type coercion.
- `patch_summary_name_status`: git `diff --name-status` parsing for run reports.
- `retry_regression_tests`: retry policy fix with required regression-test changes.
- `safe_workspace_join`: path traversal protection for workspace file access.
- `cross_file_user_contract`: cross-file API contract repair for a serializer/model pair.
- `cli_config_docs_contract`: multi-file CLI/docs/test consistency repair for configuration
  documentation.
- `packaging_ci_contract`: multi-file packaging metadata and CI workflow repair with required
  regression-test updates.

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
- manifest provenance: task ids, per-task fingerprints, variant names, and suite signature
- compact trace analysis when `--trace-dir` is enabled
- recovery success rate per variant: `recovered_runs / runs_with_failures`, where a run
  "had failures" when any parse/tool/unknown/argument/edit-guard counter is non-zero
- `by_tag` capability breakdown: per-tag runs, successes, and success rate
- repeat-variance stability when `--repeat` is greater than 1: per-task `pass@k`, `pass^k`,
  per-repeat pass lists, and a task pass-rate standard deviation (same config reruns; API
  nondeterminism included — not a controlled-seed measurement)
- advisory per-test partial credit with `--per-test-credit`: hidden tests are additionally run
  node-by-node and reported as `hidden_test_nodes` metadata plus a variant-level
  `avg_hidden_test_node_pass_fraction`; the strict binary score is unchanged

Pass-rate confidence intervals use Wilson 95% intervals. They are computed from the runs already in
the report and do not increase the default repeat count.

### Manifest guard

`dm-agent-bench --suite <suite> --manifest-only <path>` writes the suite manifest (task
fingerprints + suite signature) without running anything. CI regenerates these manifests and
diffs them against the checked-in baselines under `bench_reports/manifest-baseline-*.json` with
`dm-agent-manifest-diff` (non-zero exit on drift). When you intentionally change a benchmark
task, regenerate the baseline in the same PR and attach the diff output.

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
