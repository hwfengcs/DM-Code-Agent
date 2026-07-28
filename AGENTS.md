# AGENTS.md

Guidance for coding agents working in this repository.

## Project Intent

DM-Code-Agent is a local-first, auditable code maintenance agent. Favor changes that improve
real repository maintenance, traceability, reproducibility, and benchmark quality.

## Development Rules

- Keep the core agent readable. Prefer small, explicit modules over large abstractions.
- **Ask first: does this have to live in the kernel?** If a feature only needs to act at a few
  fixed points, it belongs in an extension (`docs/extensions.md`), not in a new
  `--enable-xxx` flag plus an `if` branch in `ReactAgent`.
- **Never delete original data.** Compaction, truncation, and summarization may only append a
  derived record and skip the original when building context — never overwrite or drop it.
  This is what makes the agent debuggable, auditable, and ablatable.
- Do not introduce network calls into tests unless they are clearly marked as live-model tests.
- Default tests and deterministic evals must run without API keys.
- Treat session/trace files as potentially sensitive. Full LLM I/O capture must remain opt-in;
  `--trace` stays redacted and `--trace`/`--checkpoint` must not point at the same file.
- Tool replay that mutates files or runs commands must remain explicit and documented.
- Keep benchmark tasks executable with plain pytest hidden tests.
- When changing benchmark behavior, update tests and docs together.
- Do not claim evaluation numbers that were not actually run. Real SWE-bench / Docker /
  cross-model scoring is frozen.
- Do not mix a fix into a pure-refactor commit — it destroys the "eval identical field by
  field" check that makes the refactor verifiable.

## Verification

Before considering a change complete, run:

```bash
python -m compileall dm_agent main.py tests
python -m pytest
python -m dm_agent.evals.cli --variant full --task direct_finish
python -m dm_agent.benchmarks.cli --suite maintenance --list
python -m ruff check .
python -m black --check .
python -m mypy dm_agent
```

CI installs from `uv.lock` (`uv sync --frozen --extra dev`) and runs the same commands via
`uv run --frozen`. If you change dependencies in `pyproject.toml`, re-run `uv lock` and commit
the updated `uv.lock` — CI fails on `uv lock --check` otherwise.

## Important Modules

- `dm_agent/core/agent.py`: ReAct loop and agent assembly. Per-step concerns live in sibling
  modules and are wired in as collaborators: `context_window.py` (message building and
  compression), `response_parser.py` (fault-tolerant JSON parsing), `tool_invoker.py` (the
  validate → hook → backup → execute → truncate chain), `completion.py` (finish gating and
  result formatting), `replan.py` (failure signatures and replanning), `persistence.py`
  (checkpoint codec and pre-write backup), `observation.py`, `prompting.py`, `run_state.py`.
- `dm_agent/core/events.py` + `capabilities.py`: lifecycle hooks and the capability contract.
  Optional behaviors (Critic, circuit breaker, Reflexion) are extensions, not kernel branches.
- `dm_agent/extensions/`: `ExtensionAPI` + registry, three-source discovery
  (`discovery.py`), project trust store (`trust.py`), and the built-in capabilities under
  `capabilities/`.
- `dm_agent/tracing/`: append-only JSONL session log — `writer.py` (entry ids, privacy tiers),
  `session.py` (read-side normalization, `rebuild_context`), `summary.py` / `analysis.py`
  (deterministic algorithms), `render.py` (human/JSON/Markdown output), `replay.py` / `fork.py`
  (explicit actions), and the thin `cli.py` parser/dispatcher.
- `dm_agent/benchmarks/`: coding and maintenance benchmark suites.
- `dm_agent/evals/`: deterministic and live-model agent evals.
- `dm_agent/tools/`: file, execution, test, lint, and code-analysis tools.
- `dm_agent/tools/code_index_tools.py`: repository-level Python symbol/dependency index tools.
- `dm_agent/cli/`: user-facing `dm-agent` CLI and outer-layer runtime assembly.
- `main.py`: thin compatibility shim for `python main.py`.

Architecture in prose (the authoritative source, not the drawio/png):
[`docs/architecture.md`](docs/architecture.md).

## Layering

Dependencies must point one way only. Ruff's `TID251` enforces it in CI; the contract and its
rationale live in `pyproject.toml` under `[tool.ruff.lint.flake8-tidy-imports.banned-api]`.

```
clients → tools → tracing → core → extensions → cli
```

`core` / `tools` / `clients` / `memory` / `tracing` / `evals` / `benchmarks` must not import
`dm_agent.cli`, and nothing may import the top-level `main` module.

## Style

- Python 3.10+.
- Black line length: 100.
- Ruff lints with `E`, `F`, `I`, `UP`, `B`, `SIM`, `TID`, `RUF`. `E501` and `RUF001`-`RUF003`
  are disabled on purpose (reasons documented in `pyproject.toml`); do not add `# noqa` to
  source files — disable a rule in config with a written justification instead.
- mypy runs over `dm_agent`; `dm_agent.tools.*` and `dm_agent.clients.*` additionally enforce
  `disallow_untyped_defs`. New code in those two packages must be fully annotated.
- Keep tests focused on behavior and avoid brittle stdout assertions unless validating CLI UX.
