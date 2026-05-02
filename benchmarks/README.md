# DM-Code-Agent Coding Benchmarks

This directory documents the L2 capability benchmark suite. Unlike the deterministic evals,
these tasks are scored by hidden tests that are injected only after the agent finishes.

## Run

List tasks:

```bash
dm-agent-bench --list
```

Run one live DeepSeek task:

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key
dm-agent-bench --provider deepseek --task slugify_cleanup
```

Run the full default benchmark and write reports:

```bash
dm-agent-bench --provider deepseek \
  --output bench_reports/deepseek_coding.json \
  --markdown bench_reports/deepseek_coding.md
```

Run ablations:

```bash
dm-agent-bench --provider deepseek --all-variants
```

## What It Measures

- Hidden-test pass rate
- Average agent steps
- Average tool calls
- Real provider request count
- Real token usage when the provider returns usage metadata
- Planning / skills / compression ablations

The benchmark is intentionally harder than the L1 eval suite: prompts are less tool-explicit,
tasks include visible and hidden tests, and success is based on executable behavior rather than
final-answer keywords.
