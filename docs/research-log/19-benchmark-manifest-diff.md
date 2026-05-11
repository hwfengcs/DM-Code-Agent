# 19 - Benchmark manifest diff CLI

## TL;DR

`dm-agent-manifest-diff` compares two existing benchmark JSON reports before anyone compares their
scores. It checks suite signatures, task fingerprints, task membership, and variant names without
rerunning benchmarks or touching live services.

## Context

Benchmark reports now include manifest provenance, but humans can still paste two pass rates into a
table even when those reports were produced from different task sets. That is especially risky while
the maintenance suite is evolving: adding a task, changing hidden tests, or changing changed-file
constraints should make score comparisons visibly suspect.

The new CLI turns the manifest into an offline guardrail.

## What Changed

- `dm_agent/benchmarks/manifest_diff.py`
  - loads two benchmark JSON reports;
  - compares `manifest.suite_signature`, suite name, task fingerprints, and variant names;
  - renders Markdown by default or JSON with `--json`;
  - exits `0` for compatible reports, `1` for manifest drift, and `2` for invalid inputs.
- `pyproject.toml`
  - adds the `dm-agent-manifest-diff` console entry point.
- Tests cover matching reports, suite drift, task membership drift, variant drift, fingerprint drift,
  and CLI exit codes.

## Example

```bash
dm-agent-manifest-diff bench_reports/baseline.json bench_reports/experiment.json
```

For automation:

```bash
dm-agent-manifest-diff bench_reports/baseline.json bench_reports/experiment.json --json
```

## Why It Is Default-Safe

The command reads files only. It does not run an agent, a verifier, SWE-bench, Docker, a package
installer, or a model provider. A nonzero drift exit is deliberate: it lets CI or local scripts stop
before presenting misleading score deltas.

## Keyless Checks

```bash
python -m pytest tests/test_coding_benchmarks.py
python -m ruff check dm_agent/benchmarks/manifest_diff.py tests/test_coding_benchmarks.py
python -m black --check dm_agent/benchmarks/manifest_diff.py tests/test_coding_benchmarks.py
```

## Open Questions / Next Bets

- Add economics-report manifest guards so multi-report cost tables warn on suite-signature drift.
- Surface manifest summaries in benchmark Markdown reports.
- Add a trace-analysis Markdown report for shareable run-health reviews.
