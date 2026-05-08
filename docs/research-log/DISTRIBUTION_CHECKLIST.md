# Distribution checklist

This is the local launch checklist for DM-Code-Agent v2. It is a plan, not a record of completed
external posting.

## GitHub release

- Tag `v2.0.0` after CI passes.
- Release title: `DM-Code-Agent v2: auditable local code agent with Reflexion, RAG, critic review`.
- Attach links to:
  - `README.md`
  - `docs/research-log/06-final-writeup.md`
  - `bench_reports/swebench_lite_baseline.md`
  - `bench_reports/economics.md`
- State clearly that the SWE-bench Lite number is Tier-1 host verifier, not leaderboard comparable.

## Blog / long-form post

- Publish the final write-up from `06-final-writeup.md`.
- Keep the headline focused on the engineering artifact, not on unverified score improvements.
- Include the frozen baseline caveat near the first SWE-bench mention.

## Short posts

- X / Twitter: one thread with architecture, trace screenshot/GIF, and the frozen baseline note.
- Jike / Weibo: short Chinese summary with the research-log index.
- Reddit / Hacker News: post only after a clean install smoke test from a fresh clone.

## Awesome lists

- `awesome-llm`
- `awesome-ai-agents`
- `awesome-mcp`

Suggested description:

> Local-first Python code agent with JSONL trace/replay, MCP tools, hidden-test benchmarks, SWE-bench
> Lite Tier-1 harness, and default-off Reflexion/RAG/Critic/Self-Consistency modules.

## Demo asset

The intended 90-second demo flow:

1. Fresh checkout and `pip install -e ".[dev]"`.
2. `dm-agent-bench --suite maintenance --list`.
3. Show one deterministic eval or benchmark manifest.
4. Show trace replay.
5. Show `dm-agent-economics` regenerating `bench_reports/economics.md`.

Do not present a new SWE-bench score unless a permitted real evaluation has been run.
