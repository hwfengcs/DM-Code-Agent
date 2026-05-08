# DM-Code-Agent v2.0.0 release notes

## Summary

DM-Code-Agent v2.0.0 is a local-first, auditable Python code-agent baseline with:

- JSONL trace/replay.
- Hidden-test coding and maintenance benchmarks.
- SWE-bench Lite Tier-1 harness and frozen 50-instance baseline.
- Default-off Reflexion, Hybrid RAG, Critic, Self-Consistency, and Adaptive Replanning modules.
- Offline benchmark token economics.

## Public Evaluation Caveat

The published SWE-bench Lite number remains the P1 Tier-1 host-verifier baseline:

- `0/50` resolved.
- `36/50` patches applied.
- Not leaderboard-comparable.

No Docker/Tier-2 SWE-bench, real cross-model sweep, or v2 algorithm score-lift claim is included in
this release.

## Release Smoke Commands

```bash
python -m build
python -m pytest
python -m ruff check dm_agent tests
python -m black --check .
python -m dm_agent.benchmarks.cli --list
python -m dm_agent.benchmarks.cli --suite maintenance --list
python -m dm_agent.benchmarks.economics bench_reports/swebench_lite_baseline.json \
  --label swebench-tier1-baseline \
  --cost-per-1k-tokens 0.00027 \
  --output-json bench_reports/economics.json \
  --output-md bench_reports/economics.md
```

## New Benchmark Plumbing

Generic coding/maintenance benchmarks now expose default-off switches for local smoke experiments:

```bash
dm-agent-bench --suite maintenance \
  --enable-rag \
  --rag-top-k 5 \
  --enable-critic \
  --self-consistency-runs 3 \
  --self-consistency-strategy test_pass
```

These switches can call real LLMs when used in live benchmark runs. CI only covers keyless parsing
and fake-result plumbing. SWE-bench Lite self-consistency remains blocked while real SWE-bench
evaluation is frozen.

## Tag Checklist

- Confirm `pyproject.toml` and `dm_agent/__init__.py` both show `2.0.0`.
- Confirm `CHANGELOG.md` has a `[2.0.0]` section.
- Confirm `README.md` and `README_EN.md` include the frozen SWE-bench caveat.
- Tag after CI passes: `git tag v2.0.0`.
