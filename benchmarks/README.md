# DM-Code-Agent Benchmarks

This directory documents the benchmark entry points. The implementation lives in
`dm_agent.benchmarks`.

## Suites

- `coding`: compact hidden-test coding tasks.
- `maintenance`: repository-maintenance tasks with edge cases and changed-file constraints.

## Commands

```bash
dm-agent-bench --list
dm-agent-bench --suite maintenance --list
```

Run one live maintenance task:

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key
dm-agent-bench --suite maintenance --provider deepseek --task config_precedence
```

Write reports:

```bash
dm-agent-bench --suite maintenance --provider deepseek \
  --output bench_reports/maintenance.json \
  --markdown bench_reports/maintenance.md \
  --trace-dir bench_reports/traces
```

Run ablations:

```bash
dm-agent-bench --suite maintenance --provider deepseek --all-variants
```

## What It Measures

- Strict pass rate
- Hidden-test pass rate
- Agent completion rate
- Average steps
- Average tool calls
- Average changed files
- Real provider request count
- Token usage when returned by the provider
- Changed-file constraint violations
- Optional per-run trace files

The maintenance suite is intended to be more practical than puzzle-style coding tasks: it
checks configuration precedence, retry policy regression tests, patch summaries, safe workspace
path handling, and cross-file API contracts.
