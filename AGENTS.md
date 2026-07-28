# AGENTS.md

Guidance for coding agents working in this repository.

## Project Intent

DM-Code-Agent is a local-first, auditable code maintenance agent. Favor changes that improve
real repository maintenance, traceability, reproducibility, and benchmark quality.

## Development Rules

- Keep the core agent readable. Prefer small, explicit modules over large abstractions.
- Do not introduce network calls into tests unless they are clearly marked as live-model tests.
- Default tests and deterministic evals must run without API keys.
- Treat trace files as potentially sensitive. Full LLM I/O capture must remain opt-in.
- Tool replay that mutates files or runs commands must remain explicit and documented.
- Keep benchmark tasks executable with plain pytest hidden tests.
- When changing benchmark behavior, update tests and docs together.

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
- `dm_agent/tracing/`: JSONL trace writing, viewing, and replay.
- `dm_agent/benchmarks/`: coding and maintenance benchmark suites.
- `dm_agent/evals/`: deterministic and live-model agent evals.
- `dm_agent/tools/`: file, execution, test, lint, and code-analysis tools.
- `dm_agent/tools/code_index_tools.py`: repository-level Python symbol/dependency index tools.
- `dm_agent/cli/`: user-facing `dm-agent` CLI and outer-layer runtime assembly.
- `main.py`: thin compatibility shim for `python main.py`.

## Style

- Python 3.10+.
- Black line length: 100.
- Ruff lints with `E`, `F`, `I`, `UP`, `B`, `SIM`, `TID`, `RUF`. `E501` and `RUF001`-`RUF003`
  are disabled on purpose (reasons documented in `pyproject.toml`); do not add `# noqa` to
  source files — disable a rule in config with a written justification instead.
- mypy runs over `dm_agent`; `dm_agent.tools.*` and `dm_agent.clients.*` additionally enforce
  `disallow_untyped_defs`. New code in those two packages must be fully annotated.
- Keep tests focused on behavior and avoid brittle stdout assertions unless validating CLI UX.
