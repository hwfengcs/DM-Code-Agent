# 21 - Trace-analysis Markdown reports

## TL;DR

`dm-agent-trace analyze-dir` can now write a shareable Markdown report with `--markdown PATH`.
The report summarizes trace health, verification gaps, final failure stages, and per-trace status
without including raw prompts, observations, tool outputs, or final answers.

## Context

Directory-level trace analysis already produced aggregate JSON and terminal output. That is useful
for local debugging, but less useful when sharing benchmark run health in a PR, release note, or
interview portfolio. A Markdown report makes trace review portable while keeping the privacy
boundary clear.

## What Changed

- `dm-agent-trace analyze-dir TRACE_DIR --markdown report.md`
- `render_trace_directory_markdown(report)` for programmatic rendering
- `dm_agent.tracing.__all__` exports the renderer
- Tests verify:
  - Markdown is written by the CLI
  - aggregate health and verification counts appear
  - trace filenames appear
  - raw task prompt, observation text, and final answer text do not appear

## Privacy Boundary

The report intentionally uses the compact analyzer output:

- trace path
- status
- health grade
- final failure stage
- verification-gap boolean
- replan count

It does not render step observations, tool outputs, action inputs, final answers, or prompts. The
underlying JSONL traces may still contain sensitive development artifacts, so this report is a
summary layer rather than a trace sanitizer.

## Keyless Checks

```bash
python -m pytest tests/test_tracing.py
python -m ruff check dm_agent/tracing/cli.py dm_agent/tracing/__init__.py tests/test_tracing.py
python -m black --check dm_agent/tracing/cli.py dm_agent/tracing/__init__.py tests/test_tracing.py
```

## Open Questions / Next Bets

- Link generated trace-analysis Markdown from benchmark Markdown reports when `--trace-dir` is used.
- Add trace-diff aggregation for baseline/candidate trace directories.
- Add optional top-N risky trace details without raw observations.
