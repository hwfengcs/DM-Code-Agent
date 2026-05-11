# 20 - Economics manifest guard

## TL;DR

`dm-agent-economics` now records manifest-guard metadata and emits a Markdown warning when input
reports have different `manifest.suite_signature` values. The report is still generated, but the
ranking is explicitly marked as potentially non-comparable.

## Context

Entry 19 added a dedicated manifest diff CLI. Economics reports have a related risk: they rank
reports by cost per success and pass rate, but those rankings are misleading if the input reports
come from different task contracts.

The economics command should remain convenient for exploratory local accounting, so the first guard
is warning-only rather than a hard failure.

## What Changed

- `build_economics_report(...)` adds `summary.manifest_guard`:
  - `warning`
  - `suite_signature_count`
  - `suite_signatures`
  - `missing_suite_signature`
- `render_markdown(...)` prints a warning block when more than one suite signature is present.
- Tests cover matching signatures, mismatched signatures, missing legacy signatures, and Markdown
  warning rendering.

## Interpretation

The warning does not prove either report is wrong. It says the cost/pass-rate ranking should not be
read as an apples-to-apples comparison unless the difference is intentional and explained.

Legacy reports without manifest data are recorded under `missing_suite_signature`, but missing data
alone does not trigger the mismatch warning. This keeps old reports readable while still surfacing
provenance gaps.

## Keyless Checks

```bash
python -m pytest tests/test_coding_benchmarks.py
python -m ruff check dm_agent/benchmarks/economics.py tests/test_coding_benchmarks.py
python -m black --check dm_agent/benchmarks/economics.py tests/test_coding_benchmarks.py
```

## Open Questions / Next Bets

- Add an optional `--fail-on-manifest-drift` flag for CI jobs.
- Render suite-signature summaries in normal benchmark Markdown reports.
- Add trace-analysis Markdown reports for shareable run-health reviews.
