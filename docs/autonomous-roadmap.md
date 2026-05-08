# Autonomous Roadmap

This file tracks local, keyless improvement opportunities found during autonomous project review.
It is not a promise of public benchmark gains; it is a work queue for code + tests + docs changes
that improve DM-Code-Agent as an auditable code-agent baseline.

## Completed

| Date | Item | Evidence |
| --- | --- | --- |
| 2026-05-08 | Trace diff CLI for offline behavioral comparison | `dm-agent-trace diff`, `tests/test_tracing.py`, `docs/research-log/07-trace-diff.md` |

## Highest ROI Backlog

| Priority | Opportunity | Why it matters | Constraints |
| ---: | --- | --- | --- |
| 1 | Trace analyzer: failure-stage attribution, verification-gap detection, trace-health hints | Converts traces from audit logs into review signals for agent regressions and benchmark triage | Must remain read-only and advisory; no tool replay by default |
| 2 | Maintenance benchmark realism: multi-file tasks, docs/CLI consistency, packaging/CI repair | Makes in-tree benchmarks look closer to daily repository work and stronger for interviews | Hidden tests must stay deterministic and keyless |
| 3 | Repeated-sample statistics for benchmark reports | Moves pass rate from point estimates toward confidence-aware ablation reporting | Do not increase default repeat count |
| 4 | Self-consistency uncertainty metadata | Explains whether a selected candidate was 3-0 obvious or 2-1 fragile | Do not change selected candidate semantics |
| 5 | Adaptive replanning repeated-failure signal | Records loops where replanning returns to the same failing action | First pass should add metadata only, not change decisions |
| 6 | Benchmark provenance and trace completeness checks | Detects task manifest drift and missing trace artifacts in reports | Hashing must canonicalize task metadata carefully |

## Frozen Unless Authorized

- Docker / Tier-2 SWE-bench verification.
- New true SWE-bench runs or real leaderboard-comparable claims.
- Cross-model live sweeps.
- External publishing, tagging, release upload, or anything requiring API keys.
