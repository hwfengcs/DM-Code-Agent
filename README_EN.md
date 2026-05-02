# DM-Code-Agent

<div align="center">

**A local-first, auditable Python Code Agent with an algorithmic backbone**

[![CI](https://github.com/hwfengcs/DM-Code-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/hwfengcs/DM-Code-Agent/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-ready-purple.svg)](MCP_GUIDE.md)
[![Trace](https://img.shields.io/badge/Trace-Replay-blueviolet.svg)](docs/tracing.md)
[![SWE-bench Lite](https://img.shields.io/badge/SWE--bench%20Lite-coming%20in%20v2-lightgrey.svg)](docs/research-log/00-kickoff.md)
[![Research Log](https://img.shields.io/badge/Research%20Log-active-orange.svg)](docs/research-log/)

[Chinese](README.md) | **English** | [Français](README_FR.md)

</div>

> **One line.** DM-Code-Agent is a code-maintenance agent that fits ReAct + Planner + Replan + Trace
> into ~1500 lines of readable Python. v2 adds an algorithm stack — Reflexion, Hybrid RAG, Critic,
> Self-Consistency, Adaptive Replanning — and publishes a SWE-bench Lite score.
>
> The point is not yet another chat black box. It is a code agent that engineers can read, reproduce,
> extend, and benchmark against.

## Why this project

- **Auditable.** Every plan, tool call, and observation is written to a JSONL trace. Trace ships with
  dry replay and explicit tool replay; debugging does not require asking the model again.
- **Benchmarked.** Coding and maintenance hidden-test suites are in-tree. SWE-bench Lite lands in v2
  Phase 1. Every ablation table links to its raw `bench_reports/*.json`.
- **Algorithmic (v2).** Not "call GPT-4 and write a ReAct loop." Reflexion, Hybrid RAG, Critic,
  Self-Consistency, and Adaptive Replanning are first-class modules with their own ablations. See
  `docs/research-log/` for the design rationale and the failures behind each one.
- **Extensible.** Built-in skill system + MCP integration: domain prompts and specialized tools
  activate on task signals. Four LLM providers (DeepSeek/OpenAI/Claude/Gemini), plus arbitrary
  `base_url`.

## How it compares (numbers will be filled by v2)

| Dimension | DM-Code-Agent | Aider | OpenHands | SWE-agent | smolagents |
| --- | --- | --- | --- | --- | --- |
| Local-first (no sandbox required) | ✅ | ✅ | docker | docker | ✅ |
| Trace + Replay | ✅ JSONL + dry/tool replay | git diff | server log | trajectory | weak |
| Reflexion / Critic / Self-Consistency | ✅ v2 | ❌ | partial | ❌ | ❌ |
| Hybrid BM25 + embedding RAG | ✅ v2 (opt-in) | repo-map | partial | retrieval | ❌ |
| MCP integration | ✅ | ❌ | ✅ | ❌ | ❌ |
| In-tree maintenance benchmark | ✅ 5+ tasks | ❌ | ❌ | SWE-bench | ❌ |
| Public SWE-bench Lite score | 🔄 v2 P1 in progress | ❌ | ✅ | ✅ | ❌ |
| Core LOC | ~1500 | ~10k | ~50k | ~5k | ~3k |
| License | MIT | Apache-2.0 | MIT | MIT | Apache-2.0 |

> SWE-bench numbers and ablation data drop in v2 phases 1-5. Track the progress in
> [docs/research-log/](docs/research-log/) and [CHANGELOG.md](CHANGELOG.md).

## Algorithm Highlights (v2 roadmap)

| Module | Status | What it does | Devlog |
| --- | --- | --- | --- |
| ReAct + Planner + Replan | ✅ v1.5 | Base loop, 3-8 step plan, replan on failure | [00](docs/research-log/00-kickoff.md) |
| SWE-bench Lite suite | 🔄 P1 | 50-instance subset, DeepSeek baseline, failure-mode analysis | 01 (soon) |
| Reflexion (episodic memory) | 🔄 P2 | Failed trial → lesson → next-trial prompt; pass@k reporting | 02 (soon) |
| Hybrid RAG (BM25 + embeddings + RRF) | 🔄 P3 | Function-granularity index, dual recall, top-K injection | 03 (soon) |
| Critic + Self-Consistency | 🔄 P4 | Independent peer-review LLM + N-candidate selection (majority vote / critic score / test pass) | 04 (soon) |
| Adaptive Replanning + Token economics | 🔄 P5 | Error-type-aware replan strategy, cross-model cost-per-success table | 05 (soon) |

## Research Log

Every non-trivial design decision in DM-Code-Agent ships with a devlog: motivation, experiments,
ablation, what broke, what is next. Entry point: [`docs/research-log/`](docs/research-log/).

Published:

- [00 — Kickoff: Why a v2 algorithm-track upgrade?](docs/research-log/00-kickoff.md)

---

DM-Code-Agent is a lightweight Code Agent for real repository maintenance work. It runs in a
local workspace, calls file/search/test/lint/code-analysis/MCP tools, and records structured
JSONL traces so each decision can be inspected, replayed, and benchmarked.

It is designed to be a developer tool you can audit rather than a black-box coding chatbot.

## Use Cases

- Fix small and medium bugs, then run verification commands.
- Add regression tests instead of only patching visible cases.
- Analyze project structure, function signatures, dependencies, and code metrics.
- Perform small refactors or documentation consistency fixes.
- Produce trace and benchmark reports for agent quality review.

## Capabilities

| Capability | Description |
| --- | --- |
| ReAct Agent | The model emits `thought/action/action_input`; the agent executes tools and feeds observations back |
| Task Planner | Generates a 3-8 step plan and can replan after failures |
| Tool System | File IO, search, Python/Shell execution, tests, linting, AST, and code metrics |
| Code Index | Repository-level Python symbol index, symbol search, and local dependency graph |
| Trace / Replay | JSONL traces for run, plan, LLM-call summary, tool call, step, replan, and final result |
| Multi-LLM | DeepSeek, OpenAI, Claude, Gemini, and custom `base_url` |
| MCP Integration | Attach Playwright, Context7, filesystem, SQLite, and other MCP servers |
| Skills | Activate domain-specific prompts and tools by task signals |
| Evals | Keyless deterministic evals for JSON repair, tool recovery, replan, and skill activation |
| Maintenance Benchmarks | Hidden-test repository maintenance tasks with changed-file constraints |

## Quick Start

```bash
git clone https://github.com/hwfengcs/DM-Code-Agent.git
cd DM-Code-Agent

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

copy .env.example .env
dm-agent --help
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
dm-agent --help
```

Add at least one provider API key to `.env`, then run:

```bash
dm-agent "Analyze this repository and identify the modules that most need tests" --provider deepseek --show-steps
```

## Trace And Replay

By default, traces avoid full prompt/raw-response capture and store a safer audit summary:

```bash
dm-agent "Fix retry.py retry boundaries and run tests" \
  --provider deepseek \
  --trace traces/retry-fix.jsonl \
  --report reports/retry-fix.md

dm-agent-trace view traces/retry-fix.jsonl
dm-agent-trace replay traces/retry-fix.jsonl
```

For private debugging, explicitly include full LLM I/O:

```bash
dm-agent "Explain this module" --trace traces/debug.jsonl --trace-llm-io
```

See [docs/tracing.md](docs/tracing.md).

## Benchmarks

```bash
dm-agent-bench --list
dm-agent-bench --suite maintenance --list
dm-agent-bench --suite maintenance --provider deepseek --task config_precedence \
  --output bench_reports/maintenance.json \
  --markdown bench_reports/maintenance.md \
  --trace-dir bench_reports/traces
```

Reports include hidden-test pass rate, agent completion rate, average steps, tool calls,
estimated tokens, changed files, and changed-file constraint violations. See
[docs/benchmarks.md](docs/benchmarks.md).

## Architecture

![DM-Code-Agent architecture](docs/architecture.drawio.png)

```mermaid
flowchart LR
    User[Developer CLI] --> Main[main.py]
    Main --> Agent[ReactAgent]
    Agent --> Planner[TaskPlanner]
    Agent --> Tools[Built-in Tools]
    Agent --> Skills[SkillManager]
    Agent --> Memory[ContextCompressor]
    Agent --> Trace[TraceWriter]
    Tools --> Workspace[Local Workspace]
    Tools --> MCP[MCPManager]
    Agent --> LLM[LLM Client Factory]
```

## Local Checks

```bash
python -m compileall dm_agent main.py tests
python -m pytest
python -m dm_agent.evals.cli --variant full --task direct_finish
python -m dm_agent.benchmarks.cli --suite maintenance --list
python -m ruff check .
python -m black --check .
```

## Docs

- [docs/research-log/](docs/research-log/) — design rationale, ablations, and lessons for the v2 upgrade
- [docs/product.md](docs/product.md)
- [docs/tracing.md](docs/tracing.md)
- [docs/benchmarks.md](docs/benchmarks.md)
- [MCP_GUIDE.md](MCP_GUIDE.md)
- [SKILL_GUIDE.md](SKILL_GUIDE.md)
- [CHANGELOG.md](CHANGELOG.md)

## License

MIT License. See [LICENSE](LICENSE).
