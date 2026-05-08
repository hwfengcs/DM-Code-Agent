# Autonomous Roadmap

This file tracks local, keyless improvement opportunities found during autonomous project review.
It is not a promise of public benchmark gains; it is a work queue for code + tests + docs changes
that improve DM-Code-Agent as an auditable code-agent baseline.

## Completed

| Date | Item | Evidence |
| --- | --- | --- |
| 2026-05-08 | Trace diff CLI for offline behavioral comparison | `dm-agent-trace diff`, `tests/test_tracing.py`, `docs/research-log/07-trace-diff.md` |
| 2026-05-08 | Trace analyzer for failure attribution and verification gaps | `dm-agent-trace analyze`, `tests/test_tracing.py`, `docs/research-log/08-trace-analyzer.md` |
| 2026-05-08 | Multi-file maintenance benchmark for CLI/docs/test consistency | `cli_config_docs_contract`, `tests/test_coding_benchmarks.py`, `docs/research-log/09-maintenance-realism.md` |
| 2026-05-08 | Benchmark Wilson 95% confidence intervals | `summarize_benchmark_results`, `tests/test_coding_benchmarks.py`, `docs/research-log/10-benchmark-confidence.md` |
| 2026-05-08 | Self-consistency uncertainty metadata | `SelfConsistencyRunner`, benchmark self-consistency metadata, `docs/research-log/11-self-consistency-uncertainty.md` |
| 2026-05-08 | Adaptive replanning repeated-failure signals | `ReactAgent` adaptive metadata, `replan_decision` trace fields, `docs/research-log/12-repeated-failure-signals.md` |

## Highest ROI Backlog

| Priority | Opportunity | Why it matters | Constraints |
| ---: | --- | --- | --- |
| 1 | Benchmark provenance and trace completeness checks | Detects task manifest drift and missing trace artifacts in reports | Hashing must canonicalize task metadata carefully |
| 2 | Trace analyzer aggregation over benchmark trace directories | Turns per-trace health into suite-level debugging and release-review signal | Must stay separate from hidden-test pass/fail scoring |
| 3 | Additional maintenance realism tasks: packaging/CI repair and behavior-preserving refactors | Covers more everyday OSS maintenance work beyond docs/CLI consistency | Hidden tests must stay deterministic and keyless |
| 4 | Economics report uncertainty | Carries confidence-aware interpretation into cost-per-success comparisons | Should use existing JSON reports only |
| 5 | Patch fingerprint voting for self-consistency | Makes file-editing candidates comparable beyond final-answer strings | Must be deterministic and workspace-local |
| 6 | Repeated-failure policy experiments | Uses recorded repeated-failure signals to test escalation strategies | Keep default off until deterministic evidence exists |

## Frozen Unless Authorized

- Docker / Tier-2 SWE-bench verification.
- New true SWE-bench runs or real leaderboard-comparable claims.
- Cross-model live sweeps.
- External publishing, tagging, release upload, or anything requiring API keys.
