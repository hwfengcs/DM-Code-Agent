# Product Direction

DM-Code-Agent is a local-first code maintenance agent. The product goal is not to hide the
agent behind a chat UI, but to make automated code changes auditable enough that a developer
can decide whether to trust them.

## Target Users

- Developers who want a small agent that can run inside a repository without adopting a large
  framework.
- Researchers and builders who need a readable baseline for planning, tool use, recovery, and
  code-maintenance evals.
- Teams experimenting with MCP tools and local automation who still need traceability.

## Core Jobs

1. Inspect a repository and explain the relevant modules.
2. Make a small code change with tests.
3. Recover from missing files, invalid tool arguments, and failed commands.
4. Build a code index to find symbols and local dependencies before editing.
5. Produce a trace that shows what happened and why.
6. Run a benchmark that measures hidden-test success and operational behavior.

## Non-Goals

- Replacing large IDE agents.
- Running unbounded autonomous edits without review.
- Hiding prompts, tool observations, and verification results.

## Product Principles

- Local workspace first: file and command behavior should be explicit.
- Auditability over magic: every run should be explainable after the fact.
- Reproducible evals: benchmark tasks should be executable and scored by behavior.
- Small surface area: prefer a readable core over a large abstraction stack.
- Safe defaults: full LLM I/O capture and tool replay execution must be opt-in.

## Current Maturity

The project is suitable for local experiments, repository analysis, small maintenance tasks,
and agent behavior research. It is not yet a hardened unattended production system. Trace
and benchmark work should continue toward stronger sandboxing, richer run reports, and
cross-model comparisons.
