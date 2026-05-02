# 00 — Kickoff: Why a v2 algorithm-track upgrade?

> **TL;DR.** DM-Code-Agent v1.5 is a clean, readable ReAct + Planner code
> agent, but it lacks (a) a public industry-standard score, (b) algorithmic
> differentiation against modern coding agents, and (c) the kind of
> "shop window" that converts repo visitors into stars and contributors. This
> log opens a 3-week upgrade aimed at a public SWE-bench Lite baseline,
> Reflexion / Hybrid RAG / Critic / Self-Consistency / Adaptive Replanning,
> and a thorough README/Devlog rewrite.

## Context

Where v1.5 stands today:

- **Architecture**: ReAct loop, planner with replan, context compression,
  optional MCP tools, skill activation, JSONL trace, dry replay, opt-in tool
  replay. CI on Linux + Windows, Python 3.10/3.11/3.12.
- **Evaluation surface**: keyless deterministic evals; coding benchmark suite
  (8 tasks); maintenance benchmark suite (5 tasks). Last public report
  on the coding suite (`bench_reports/deepseek_coding.md`) shows
  `pass=50.0% / hidden=66.7% / completion=66.7%` over 6 DeepSeek runs.
- **Distribution**: solid CONTRIBUTING / SECURITY / AGENTS docs, trilingual
  README (zh/en/fr).

Where v1.5 falls short for an "AI agent algorithm engineer" portfolio:

1. **No industry calibration.** A reader cannot tell whether 50% on six
   self-authored coding tasks is good. SWE-bench Lite is the de facto public
   benchmark; not having a number on it is a credibility gap.
2. **No algorithm differentiation.** The current loop is "ReAct + planner +
   replan", which by 2026 is a baseline. Reflexion, retrieval-augmented
   context, critic agents, self-consistency, and adaptive recovery are now
   table stakes for serious code agents.
3. **No "thinking surface".** There is no place where a reader can watch the
   designer reason about trade-offs. README is feature-list-shaped. Without a
   devlog, every new visitor has to re-derive the project's intent from code.

## Goals (3 weeks)

| # | Goal | Verifier |
| --- | --- | --- |
| G1 | Public SWE-bench Lite baseline + failure-mode analysis | `bench_reports/swebench_lite_baseline.md` + README badge |
| G2 | Reflexion mechanism with measurable lift | `bench_reports/swebench_lite_reflexion_ablation.md` |
| G3 | Hybrid BM25+embedding retriever, opt-in | `bench_reports/swebench_lite_rag_ablation.md` |
| G4 | Critic agent + self-consistency strategies | `bench_reports/swebench_lite_full_ablation.md` |
| G5 | Adaptive replanning + cross-model economics | `bench_reports/swebench_lite_cross_model.md` |
| G6 | README rewrite with hero demo, comparison table, research log linkage | `README.md`, `docs/research-log/06-final-writeup.md` |

Stretch: ≥50 stars, ≥1 external citation, 1 published blog post, 1
HuggingFace Space demo within 90 days of v2.0.0.

## Constraints

- **Time budget**: 2-3 weeks of evening / weekend work.
- **API budget**: ≈$50-100 across DeepSeek + Claude + GPT-4o-mini + Gemini
  Flash for benchmarking. DeepSeek v3 carries the heavy 50-instance runs.
- **Repo size**: every new module must remain readable. The agent core lives
  inside `dm_agent/core/`, around 800 LOC today. The end goal is to keep it
  under ≈1500 LOC even after Reflexion / Critic / Self-Consistency, with
  retrieval and benchmarks living in their own packages.
- **Defaults are conservative**: Reflexion, Critic, RAG are all default-off.
  Users opt into them via flags. Trace defaults remain redacted, opt-in
  full-IO. No default tool replay. No default shell escalation.

## Roadmap

| Phase | Days | Output | Devlog |
| --- | --- | --- | --- |
| P0 | 1-2 | Governance, code cleanup, README hero placeholder | this entry |
| P1 | 3-6 | SWE-bench Lite suite + 50-instance baseline | 01 |
| P2 | 7-9 | Reflexion module + multi-trial ablation | 02 |
| P3 | 10-13 | Hybrid RAG retriever + 4-config ablation | 03 |
| P4 | 14-16 | Critic + Self-Consistency + 5-config ablation | 04 |
| P5 | 17-19 | Adaptive replan + cross-model economics | 05 |
| P6 | 20-21 | README v2, demo, blog, distribution | 06 |

## Risk register

- **SWE-bench score is low (<5%)**. We publish anyway. The point of the
  baseline is to anchor relative improvements in P2-P5; an honest low number
  with strong ablations beats a polished claim with no number.
- **Embedding dependency bloat**. `sentence-transformers` ships with PyTorch.
  Mitigation: gate behind a `[rag]` extra; document the install footprint;
  keep the BM25 path usable on its own.
- **Reflexion / Critic increase latency and tokens**. Mitigation: report
  cost-per-success in P5 economics tables, not just pass rate. Default off.
- **Time overruns**. Mitigation: P0/P1/P2 are committed; P3/P4/P5 can be
  dropped or downgraded in scope (e.g., BM25-only retriever if embedding
  install proves too heavy on common dev machines).

## Open questions / next bets

- *Sampling for SWE-bench Lite 50.* Should we stratify by repo, by patch
  size, or by `FAIL_TO_PASS` count? Decision to be made and recorded in
  entry 01 with the seed.
- *Reflexion granularity.* Per-trial reflection (Shinn 2023) vs per-step
  reflection. We will start with per-trial because it composes cleanly with
  the existing benchmark loop, then revisit if data is noisy.
- *Retriever indexing unit.* Function vs file vs symbol-pair (Aider-style).
  We will start with function granularity using existing
  `dm_agent/tools/code_index_tools.py` to avoid re-walking the tree.

## Status

This entry is **active** and may be edited as the kickoff stabilizes. Once
P1 lands, this file is frozen and further changes go into 01+.
