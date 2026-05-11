# Research Log

This directory is the public devlog of DM-Code-Agent's algorithm-track upgrade.

It is not a tutorial. It is a chronological record of:

- the problems we noticed,
- the algorithms or designs we picked to address them,
- the experiments we ran (with seeds, configs, and ablations),
- the things that did not work, and
- the next bets.

The intent is to make the agent's evolution **inspectable**, the same way
JSONL traces make a single run inspectable. If you want to know **why** the
project looks the way it does, the answer should be reachable from one of
these entries.

## Index

| # | Title | Phase | Status |
| --- | --- | --- | --- |
| [00](00-kickoff.md) | Why this upgrade — motivation, goals, constraints | P0 | active |
| [01](01-swebench-baseline.md) | SWE-bench Lite harness, sampling, and the road to numbers | P1 | active |
| [02](02-reflexion.md) | Reflexion: episodic memory across trials | P2 | implementation landed; ablation pending |
| [03](03-rag.md) | Hybrid retrieval (BM25 + embeddings) for repository-scale context | P3 | implementation landed; ablation pending |
| [04](04-critic-and-consistency.md) | Critic agent and self-consistency selection | P4 | implementation landed; ablation pending |
| [05](05-adaptive-and-economics.md) | Adaptive replanning and token economics | P5 | implementation landed; real cross-model eval frozen |
| [06](06-final-writeup.md) | Final write-up: what worked, what didn't, what's next | P6 | published |
| [07](07-trace-diff.md) | Trace diff for offline behavioral comparison | post-v2 | implementation landed |
| [08](08-trace-analyzer.md) | Trace analyzer for failure attribution and verification gaps | post-v2 | implementation landed |
| [09](09-maintenance-realism.md) | More realistic maintenance benchmark tasks | post-v2 | implementation landed |
| [10](10-benchmark-confidence.md) | Benchmark confidence intervals for repeated samples | post-v2 | implementation landed |
| [11](11-self-consistency-uncertainty.md) | Self-consistency uncertainty metadata | post-v2 | implementation landed |
| [12](12-repeated-failure-signals.md) | Adaptive replanning repeated-failure signals | post-v2 | implementation landed |
| [13](13-benchmark-provenance.md) | Benchmark manifest provenance and suite signatures | post-v2 | implementation landed |
| [14](14-benchmark-trace-analysis.md) | Benchmark trace-analysis metadata | post-v2 | implementation landed |
| [15](15-trace-analysis-aggregation.md) | Trace directory analysis aggregation | post-v2 | implementation landed |
| [16](16-economics-uncertainty.md) | Confidence-aware token economics reports | post-v2 | implementation landed |
| [17](17-packaging-ci-maintenance.md) | Packaging and CI maintenance benchmark task | post-v2 | implementation landed |
| [18](18-self-consistency-patch-fingerprint.md) | Patch-fingerprint self-consistency voting | post-v2 | implementation landed |
| [19](19-benchmark-manifest-diff.md) | Benchmark manifest diff CLI | post-v2 | implementation landed |
| [20](20-economics-manifest-guard.md) | Economics manifest guard | post-v2 | implementation landed |
| [21](21-trace-analysis-markdown.md) | Trace-analysis Markdown reports | post-v2 | implementation landed |
| [22](22-repeated-failure-policy-experiment.md) | Repeated-failure policy experiment | post-v2 | implementation landed |
| [Distribution](DISTRIBUTION_CHECKLIST.md) | Launch checklist and external posting plan | P6 | local checklist |
| [Interview](INTERVIEW_TALKING_POINTS.md) | Resume/interview talking points | P6 | private prep notes |

## Conventions

- Each entry is a single Markdown file `NN-slug.md`, ordered by date.
- Numbers are stable. Do not renumber after publication.
- Each entry begins with a short `## TL;DR`, then `## Context`, the work,
  ablation tables, and `## Open questions / next bets`.
- Ablation tables embed enough to reproduce: model, provider, dataset slice,
  seed, configuration flags, raw `bench_reports/*.json` path.
- Failures are first-class content. Negative results are kept in.

## Reproducing

Every ablation table in this log links to a JSON in `bench_reports/`. To
reproduce, follow the command shown in the entry; the numbers should match
within sampling noise. If they do not, please open an issue and tag the entry.
