# 09 — More realistic maintenance benchmark tasks

## TL;DR

The maintenance suite now includes `cli_config_docs_contract`, a multi-file task that requires a
code fix, documentation sync, and regression-test updates. It is still keyless and deterministic,
but it looks more like everyday open-source maintenance than a single-function puzzle.

## Context

The original maintenance suite already covered configuration precedence, patch summary parsing,
retry regression tests, path traversal protection, and a cross-file serialization contract. That is
stronger than toy coding tasks, but most tasks still had one dominant production file and only one
kind of artifact to repair.

For an agent portfolio, the benchmark should show that the harness can score the kinds of work
maintainers actually review:

- implementation behavior,
- docs consistency,
- regression-test coverage,
- allowed/required changed-file constraints.

## New Task

`cli_config_docs_contract` sets up a small repository with:

- `cli_docs.py`: source-of-truth CLI configuration options and a broken Markdown table renderer.
- `docs/configuration.md`: stale generated docs between `CONFIG_TABLE` markers.
- `tests/test_public_cli_docs.py`: weak public coverage that only checks two options.

The prompt asks the agent to:

1. Include every `CONFIG_OPTIONS` entry in `render_config_table`.
2. Sort rows by flag.
3. Render option, env, and default values as code.
4. Embed the generated table in docs under the marker.
5. Add regression coverage so future options cannot silently disappear.

The hidden tests verify all five points, and `required_changed_files` forces production code, docs,
and tests to change.

## Why This Helps

This task exercises a different maintenance skill than bug-fix-only tasks. It rewards agents that
inspect the source of truth, update docs from code, and add future-proof tests instead of patching
only visible assertions.

It also makes benchmark reports more persuasive in interviews: the changed-file constraints show
that the benchmark is not only checking runtime behavior, but also the maintenance contract around
documentation and tests.

## Keyless Checks

```bash
python -m pytest tests/test_coding_benchmarks.py
python -m ruff check dm_agent/benchmarks/tasks.py tests/test_coding_benchmarks.py
python -m black --check dm_agent/benchmarks/tasks.py tests/test_coding_benchmarks.py
```

## Open Questions / Next Bets

- Add a CI/packaging repair task that modifies project metadata and a workflow-like file.
- Add a behavior-preserving multi-file refactor task with hidden import-contract checks.
- Add trace analyzer fields to benchmark reports when `--trace-dir` is present.
