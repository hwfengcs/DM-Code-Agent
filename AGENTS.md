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
```

## Important Modules

- `dm_agent/core/agent.py`: ReAct loop, planning, recovery, trace event hooks.
- `dm_agent/tracing/`: JSONL trace writing, viewing, and replay.
- `dm_agent/benchmarks/`: coding and maintenance benchmark suites.
- `dm_agent/evals/`: deterministic and live-model agent evals.
- `dm_agent/tools/`: file, execution, test, lint, and code-analysis tools.
- `dm_agent/tools/code_index_tools.py`: repository-level Python symbol/dependency index tools.
- `main.py`: user-facing `dm-agent` CLI.

## Style

- Python 3.10+.
- Black line length: 100.
- Ruff currently checks high-signal syntax/import issues.
- Keep tests focused on behavior and avoid brittle stdout assertions unless validating CLI UX.
