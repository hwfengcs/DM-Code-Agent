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
| 2026-05-08 | Benchmark manifest provenance and suite signatures | `benchmark_task_fingerprint`, report `manifest`, `docs/research-log/13-benchmark-provenance.md` |
| 2026-05-08 | Benchmark trace-analysis metadata | `load_trace_analysis_for_report`, per-run `metadata.trace_analysis`, `docs/research-log/14-benchmark-trace-analysis.md` |
| 2026-05-08 | Trace directory analysis aggregation | `dm-agent-trace analyze-dir`, `analyze_trace_directory`, `docs/research-log/15-trace-analysis-aggregation.md` |
| 2026-05-08 | Confidence-aware token economics reports | `dm-agent-economics` pass-rate CI, `docs/research-log/16-economics-uncertainty.md` |
| 2026-05-11 | Packaging/CI maintenance benchmark task | `packaging_ci_contract`, `tests/test_coding_benchmarks.py`, `docs/research-log/17-packaging-ci-maintenance.md` |
| 2026-05-11 | Patch-fingerprint self-consistency voting | `SelfConsistencyRunner`, benchmark `patch_fingerprint` metadata, `docs/research-log/18-self-consistency-patch-fingerprint.md` |
| 2026-05-11 | Benchmark manifest diff CLI | `dm-agent-manifest-diff`, `diff_report_manifests`, `docs/research-log/19-benchmark-manifest-diff.md` |

## Highest ROI Backlog

| Priority | Opportunity | Why it matters | Constraints |
| ---: | --- | --- | --- |
| 1 | Repeated-failure policy experiments | Uses recorded repeated-failure signals to test escalation strategies | Keep default off until deterministic evidence exists |
| 2 | Trace analysis Markdown reports | Produces shareable trace-health summaries from directories | Avoid leaking full trace contents |
| 3 | Economics report manifest guard | Warns before ranking reports with different suite signatures | Should be overrideable for intentional comparisons |
| 4 | Additional maintenance realism tasks: behavior-preserving refactors | Covers more everyday OSS maintenance work beyond docs/CLI and packaging/CI consistency | Hidden tests must stay deterministic and keyless |
| 5 | Self-consistency report rendering | Make patch-vote metadata easier to read in benchmark Markdown | Keep full patch contents out of reports |
| 6 | Manifest-aware benchmark Markdown summaries | Surface suite signature and task-contract warnings near score tables | Avoid noisy output for matching reports |

## Frozen Unless Authorized

- Docker / Tier-2 SWE-bench verification.
- New true SWE-bench runs or real leaderboard-comparable claims.
- Cross-model live sweeps.
- External publishing, tagging, release upload, or anything requiring API keys.
