# 17 - Packaging and CI maintenance benchmark task

## TL;DR

The maintenance suite now includes `packaging_ci_contract`, a deterministic multi-file task for
repairing Python packaging metadata, dev extras, CI workflow commands, and regression tests. It
does not run a real CI service or install dependencies; hidden tests inspect the local files and
contract helper functions.

## Context

After adding `cli_config_docs_contract`, the maintenance benchmark covered docs/code/test drift,
but still did not exercise another common open-source review path: packaging and CI drift. Agent
projects often fail in mundane places such as `requires-python`, missing dev extras, incomplete
Python version matrices, or CI commands that do not match the documented local checks.

This task broadens the suite without touching Docker, true SWE-bench, network access, or live
provider calls.

## What Changed

`packaging_ci_contract` creates a temporary repository with:

- `packaging_contract.py`, a small source-of-truth helper for supported Python versions, dev
  dependencies, CI install command, and CI check commands.
- `pyproject.toml`, initially missing the Python 3.10 floor/classifier and the `ruff` / `black`
  dev dependencies.
- `.github/workflows/ci.yml`, initially missing Python 3.10, the dev-extra install command, and
  lint/format checks.
- `tests/test_public_packaging.py`, initially weak coverage that only checks pytest and one Python
  version.

The prompt requires the agent to keep all four files consistent and add regression coverage. Hidden
tests verify:

- `requires-python` is `>=3.10` and the CI matrix is exactly `3.10`, `3.11`, `3.12`.
- `pytest`, `ruff`, and `black` are all in the dev extra.
- CI installs `".[dev]"` and runs pytest, ruff, and black checks in order.
- the workflow and `pyproject.toml` agree with the helper contract.

Changed-file constraints require updates to production helper code, packaging metadata, CI config,
and public tests.

## Why It Helps

This task is closer to real repository maintenance than a single-function puzzle. It rewards agents
that inspect multiple sources of truth, align configuration surfaces, and add tests that prevent
future drift. The task also gives benchmark reports a stronger portfolio signal: the harness can
score CI and packaging repairs without relying on an external CI runner.

## Keyless Checks

```bash
python -m pytest tests/test_coding_benchmarks.py
python -m ruff check dm_agent/benchmarks/tasks.py tests/test_coding_benchmarks.py
python -m black --check dm_agent/benchmarks/tasks.py tests/test_coding_benchmarks.py
```

## Open Questions / Next Bets

- Add patch-fingerprint voting to self-consistency so file-edit candidates are compared by changes,
  not only by final-answer text.
- Add a benchmark manifest diff CLI before score comparisons.
- Add a behavior-preserving refactor task with hidden import-contract checks.
