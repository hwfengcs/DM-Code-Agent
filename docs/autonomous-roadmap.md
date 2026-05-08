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

## Highest ROI Backlog

| Priority | Opportunity | Why it matters | Constraints |
| ---: | --- | --- | --- |
| 1 | Repeated-sample statistics for benchmark reports | Moves pass rate from point estimates toward confidence-aware ablation reporting | Do not increase default repeat count |
| 2 | Self-consistency uncertainty metadata | Explains whether a selected candidate was 3-0 obvious or 2-1 fragile | Do not change selected candidate semantics |
| 3 | Adaptive replanning repeated-failure signal | Records loops where replanning returns to the same failing action | First pass should add metadata only, not change decisions |
| 4 | Benchmark provenance and trace completeness checks | Detects task manifest drift and missing trace artifacts in reports | Hashing must canonicalize task metadata carefully |
| 5 | Trace analyzer aggregation over benchmark trace directories | Turns per-trace health into suite-level debugging and release-review signal | Must stay separate from hidden-test pass/fail scoring |
| 6 | Additional maintenance realism tasks: packaging/CI repair and behavior-preserving refactors | Covers more everyday OSS maintenance work beyond docs/CLI consistency | Hidden tests must stay deterministic and keyless |

## Frozen Unless Authorized

- Docker / Tier-2 SWE-bench verification.
- New true SWE-bench runs or real leaderboard-comparable claims.
- Cross-model live sweeps.
- External publishing, tagging, release upload, or anything requiring API keys.
