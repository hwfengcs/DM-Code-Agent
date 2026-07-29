# DM-Code-Agent

<div align="center">

**Local-first · Fully auditable · The kernel is just one ReAct loop**

[![CI](https://github.com/hwfengcs/DM-Code-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/hwfengcs/DM-Code-Agent/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-301%20passed-brightgreen.svg)](tests/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/hwfengcs/DM-Code-Agent?style=flat&color=yellow)](https://github.com/hwfengcs/DM-Code-Agent/stargazers)
[![Last commit](https://img.shields.io/github/last-commit/hwfengcs/DM-Code-Agent?color=informational)](https://github.com/hwfengcs/DM-Code-Agent/commits/main)
[![Docs](https://img.shields.io/badge/Docs-docs%2F-purple.svg)](docs/)
[![Research Log](https://img.shields.io/badge/Research%20Log-32%20entries-orange.svg)](docs/research-log/)

[中文](README.md) | **English**

<img src="docs/project-overview-simple.png" alt="DM-Code-Agent overview: task → plan → ReAct loop → completion gate → delivery" width="100%">

</div>

A Python code agent you can actually **read, reproduce, and extend**. It runs in your local
workspace — reading and writing files, running tests and linters, calling MCP tools — and
records every plan, tool call, and observation into an **append-only session log**. When
something goes wrong you can replay it, diagnose it, and **fork a new run from any single step**.

Not another chat black box: the kernel is just the ReAct loop (928 lines), while Reflexion /
Critic / circuit breaking are extensions hanging off lifecycle hooks, and context compaction
**never deletes history** — so ablation conclusions can actually be verified.

> If this project is useful to you, a ⭐ helps others find it.

---

## ⚡ 60-second start

```bash
git clone https://github.com/hwfengcs/DM-Code-Agent.git && cd DM-Code-Agent
uv sync --frozen --extra dev        # or: pip install -e ".[dev]"
cp .env.example .env                # add at least one API key
```

```bash
# Run a task and keep an auditable session log
dm-agent "Fix the retry boundary in retry.py and run the tests" \
  --trace sessions/fix.jsonl --show-steps

# Diagnose that run: which step failed, did it replan and recover, did it skip verification
dm-agent-trace analyze sessions/fix.jsonl
```

**Try before you pay**: tests, deterministic evals, and benchmark manifest checks need
**no API key at all**.

```bash
python -m pytest && python -m dm_agent.evals.cli --variant full --task direct_finish
```

---

## ⭐ Six things you won't find elsewhere

### 🌳 Run history is a tree that never deletes anything

Most agents compact context by throwing history away, leaving nothing to audit. Here every
entry carries an `id` and a `parent_id`, and compaction only **appends** a derived
"I compacted" record — **not one original message is removed**. So you get:

```bash
dm-agent-trace view       sessions/fix.jsonl    # human-readable timeline
dm-agent-trace analyze    sessions/fix.jsonl    # failure stage / recovery / verification gap
dm-agent-trace diff       a.jsonl b.jsonl       # compare two runs
dm-agent-trace fork       sessions/fix.jsonl --at 4f4bdeee-0007   # branch from entry 7
dm-agent-trace replay     sessions/fix.jsonl    # explicit tool replay
dm-agent-trace analyze-dir sessions/             # aggregate across a directory
```

### 📉 Compaction has a net-benefit guard and rolls back when it loses

Compaction is **locally deterministic** (Mem0-style atomic memory) — it does not burn an extra
LLM call. More importantly it does the math: a candidate is committed only when
`estimated_tokens_after < estimated_tokens_before`, and **a candidate with no gain is rolled
back completely** (memory, cadence, and summary state all restored). A compaction proven to pay
off is reused stickily across requests and across runs, with `phase=sticky_reuse` written into
the trace so reuse is never counted as a fresh compaction.

### 🔌 Add tools / guards / providers without touching a single kernel line

Drop in a `.py` that exports `setup(api)`. Four registration methods
(`register_tool` / `register_skill` / `register_provider` / `on`) plus
**six interceptable lifecycle hooks**:

| Hook | What you can do |
| --- | --- |
| `before_tool_call` | Rewrite arguments, or return `{block, reason}` to stop a dangerous call |
| `after_tool_result` | Middleware-style rewriting of the observation |
| `before_llm_request` | Rewrite messages before they reach the model |
| `before_finish` | Veto a premature "I'm done" |
| `on_run_start` / `on_run_end` | Adjust metadata / append a prompt / `{retry: True}` for another attempt |

[`examples/block_dangerous_shell.py`](examples/block_dangerous_shell.py) is a runnable 25-line
example that blocks `rm -rf`. Discovery has five priority levels (builtin → entry_points →
user directory → project directory → `--extension`), and **project-local extensions require
explicit trust** before they load.

### 🛡️ Guardrails default ON, behavior defaults OFF

This classification is written into the project's constitution, not decided ad hoc:

| Default **ON** (infrastructure guardrails) | Default **OFF** (behavior / algorithms) |
| --- | --- |
| read-before-edit guard, observation truncation, token-budget compaction | Reflexion (reflect-and-retry) |
| Atomic writes + automatic backups, unified LLM retry | Critic completion gate, Self-Consistency |
| `--checkpoint` / `--resume` run-level resumption | Circuit breaker, adaptive replanning, LLM compression |

New users get a **safe** default configuration; researchers flip one `--enable-xxx` at a time
to run a clean ablation.

### 🔬 Full verification with no API key

| | |
| --- | --- |
| Unit tests | **301 cases**, 8.7k lines of test code (21.7k lines of source) |
| Deterministic evals | 14 tasks × 4 variants, driven by a scripted client, **zero network calls** |
| CI matrix | Ubuntu + Windows × Python 3.10 / 3.11 / 3.12 — **6 combinations** |
| Quality gates | ruff (`E F I UP B SIM TID RUF`) + black + mypy + `uv lock --check` + pre-commit |
| Layering contract | `clients → tools → tracing → core → extensions → cli`, enforced by ruff `TID251` in CI |

"Minimal kernel" is a number you can check, not a slogan: `agent.py` 1774 → **928** lines,
`main.py` 2048 → **6** lines, `tracing/cli.py` 1111 → **171** lines.

### 🧪 No inflated scores

**This project never claims an evaluation improvement it has not actually run.** Real
SWE-bench / Docker Tier-2 verifier / cross-model scoring are currently **frozen**. The
published SWE-bench Lite Tier-1 baseline is `0.0% resolved / 72.0% patch-applied` (DeepSeek,
a fixed 50-task subset, affected by host verifier noise and therefore **not comparable to the
official leaderboard**). The v2 algorithm modules only claim "code, keyless tests, and offline
reporting have landed". Full caveats in [project status](docs/project-status.md).

---

## 👀 What a real run looks like

The output below is **actually generated** (the `tool_failure_replan` deterministic eval task,
no API key needed) — a failed read triggers a replan, which then completes via another path:

```console
$ dm-agent-trace view sessions/demo.jsonl
Trace run: 4f4bdeee197d415e8fc8992c227605f9
Task: If reading missing.txt fails, create recovered.txt instead.
Status: success
Provider: deepseek
Model: deepseek-chat
Events: 22
Steps: 3

1. read_file -> 文件 missing.txt 不存在。
2. create_file -> 已将 24 个字符写入 recovered.txt。
3. task_complete -> 任务完成：recovered

Final: 任务完成：recovered
```

`analyze` doesn't just say it succeeded — it **calls out the corner it cut**: this run declared
completion without running any verification.

```console
$ dm-agent-trace analyze sessions/demo.jsonl
Trace analysis
Status: success
Primary failure stage: tool
Final failure stage: none
Recovery: failures=1, replans=1, replanned_after_failure=true, recovered=true
Verification: actions=0, before_finish=false, gap=true
Hallucination signals: edit_without_read=0, guard_blocks=0, truncations=0, missing_paths=1
Health: warning (0.80)
Issues:
- verification_gap
```

That's what "auditable" means here: **a successful task is not the same as a healthy process**,
and the difference is machine-readable.

---

## 🏗️ Architecture at a glance

```mermaid
flowchart TD
    CLI["<b>cli</b> — outermost assembler<br/>dm-agent · -eval · -bench · -trace · -economics · -manifest-diff"]
    EXT["<b>extensions</b> — ExtensionAPI · registry · five-level discovery · project trust<br/>built-in capabilities: critic_gate / circuit_breaker / reflexion_loop / self_consistency"]
    CORE["<b>core</b> — agent.py is assembly + the ReAct loop only (928 lines)<br/>context_window · response_parser · tool_invoker · completion<br/>replan · persistence · run_state · observation · prompting"]
    TRACING["<b>tracing</b> — session entry tree · append-only writes · privacy tiers · fork"]
    TOOLS["<b>tools</b> — 17 built-in tools + dynamic MCP tools"]
    CLIENTS["<b>clients</b> — deepseek / openai / claude / gemini + custom providers"]

    CLI --> EXT
    EXT -. "six interceptable lifecycle hooks" .-> CORE
    CORE --> TRACING --> TOOLS --> CLIENTS
```

Dependencies flow **one way only** (`clients → tools → tracing → core → extensions → cli`),
enforced by ruff `TID251` in CI — a `core` module importing `cli` fails the build.
The authoritative prose version is [docs/architecture.md](docs/architecture.md).

---

## 📊 v.s. similar projects

| Dimension | DM-Code-Agent | Aider | OpenHands | SWE-agent | smolagents |
| --- | --- | --- | --- | --- | --- |
| Local-first (no sandbox dependency) | ✅ | ✅ | docker | docker | ✅ |
| Session log + replay | ✅ JSONL entry tree + dry/tool replay + diff + fork | git diff | server log | trajectory | weak |
| Non-destructive context compaction | ✅ originals kept, recomputable offline | repo-map | partial | trajectory | weak |
| Reflexion / Critic / Self-Consistency | ✅ v2 (default off) | ❌ | partial | ❌ | ❌ |
| Extension system (add capabilities without kernel edits) | ✅ entry_points + directories + explicit file | ❌ | plugins | ❌ | ❌ |
| Interceptable lifecycle hooks | ✅ 6 events | ❌ | partial | ❌ | ❌ |
| MCP integration | ✅ | ❌ | ✅ | ❌ | ❌ |
| Bundled maintenance benchmark | ✅ 6+ tasks | ❌ | ❌ | SWE-bench | ❌ |
| Published SWE-bench Lite score | ⚠️ Tier-1: 0.0% (50/300 subset, non-official protocol) | ❌ | ✅ | ✅ | ❌ |
| License | MIT | Apache-2.0 | MIT | MIT | Apache-2.0 |

Comparison protocol, module status, and roadmap: [project status](docs/project-status.md).

---

## 📚 Documentation

Start at **[docs/](docs/)** for the full index. The five you will want first:

| Document | When to read it |
| --- | --- |
| [Getting started](docs/getting-started.md) | Install, configure, first task, local checks |
| [CLI reference](docs/cli.md) | Six entry points, every flag and its default |
| [Architecture](docs/architecture.md) | Layering, execution chain, hook points, session model |
| [Extensions](docs/extensions.md) | Add tools / guards / providers without kernel edits, plus the security model |
| [Sessions and traces](docs/tracing.md) | Session tree, privacy tiers, checkpoints, fork |

Motivation, experiments, and dead ends for every non-trivial design decision live in
[`docs/research-log/`](docs/research-log/) (32 entries).

> Pages under `docs/` are maintained in Chinese only. This README is the English entry point.
> Issues and PRs in English are welcome.

---

## 🤝 Contributing

Issues and PRs are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md),
[SECURITY.md](SECURITY.md), and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) first. Changes
involving an algorithmic decision or a non-trivial ablation should come with a devlog entry
under [`docs/research-log/`](docs/research-log/).

**Adding a built-in tool** touches exactly one place: `dm_agent/tools/__init__.py:_builtin_tools()`.
**Adding a third-party extension** doesn't touch the repo at all — see
[Extensions](docs/extensions.md).

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=hwfengcs/DM-Code-Agent&type=Date)](https://star-history.com/#hwfengcs/DM-Code-Agent&Date)

## License

MIT License. See [LICENSE](LICENSE).
