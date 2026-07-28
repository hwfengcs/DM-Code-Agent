# DM-Code-Agent

<div align="center">

**A local-first, auditable Python code agent with a real algorithmic skeleton**

[![CI](https://github.com/hwfengcs/DM-Code-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/hwfengcs/DM-Code-Agent/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/Docs-docs%2F-purple.svg)](docs/)
[![Research Log](https://img.shields.io/badge/Research%20Log-active-orange.svg)](docs/research-log/)

[中文](README.md) | **English**

</div>

It runs a ReAct loop in your local workspace — reading and writing files, running tests and
linters, calling MCP tools — and records every plan, tool call, and observation into an
append-only JSONL session log.

Not another chat black box, but a code-agent baseline you can read, reproduce, extend, and
benchmark against: the kernel is just the ReAct loop, while Reflexion / Critic / circuit
breaking are extensions hanging off lifecycle hooks, and context compaction never deletes
history — so ablation conclusions can actually be verified.

## Install

```bash
git clone https://github.com/hwfengcs/DM-Code-Agent.git
cd DM-Code-Agent
uv sync --frozen --extra dev        # or: pip install -e ".[dev]"
cp .env.example .env                # add at least one API key
```

## Run one

```bash
dm-agent "Analyze this project and list the modules worth testing first" --show-steps

dm-agent "Fix the retry boundary in retry.py and run the tests" --trace sessions/fix.jsonl
dm-agent-trace analyze sessions/fix.jsonl
```

Tests, deterministic evals, and benchmark manifest checks need **no API key**:

```bash
python -m pytest && python -m dm_agent.evals.cli --variant full --task direct_finish
```

## Documentation

Start at **[docs/](docs/)** for the full index. The four you will want first:

- [Getting started](docs/getting-started.md) — install, configure, first task, local checks
- [CLI reference](docs/cli.md) — six entry points, every flag and its default
- [Architecture](docs/architecture.md) — layering, execution chain, hook points, session model
- [Extensions](docs/extensions.md) — add tools / guards / providers without touching the kernel

For the comparison table and evaluation caveats, see
[project status](docs/project-status.md).
**This project never claims evaluation numbers it has not actually run.**

> Pages under `docs/` are maintained in Chinese only. This README is the English entry point.
> Issues and PRs in English are welcome.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md), [SECURITY.md](SECURITY.md),
and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) first. Changes involving an algorithmic decision
or a non-trivial ablation should come with a devlog entry under
[`docs/research-log/`](docs/research-log/).

## License

MIT License. See [LICENSE](LICENSE).
