# Changelog

All notable changes to DM-Code-Agent are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `dm-agent-trace analyze` for offline failure-stage attribution, recovery
  inspection, verification-gap detection, and advisory trace-health grades.
- `cli_config_docs_contract`, a multi-file maintenance benchmark task that
  requires implementation, docs, and regression-test changes for CLI
  configuration documentation.
- Wilson 95% confidence intervals for benchmark strict pass, hidden-test pass,
  and agent completion rates in JSON summaries and Markdown reports.
- Self-consistency uncertainty metadata for core and benchmark multi-candidate
  selection, including vote distribution, selected support, score margin,
  tie detection, disagreement reason, and confidence label.
- Adaptive replanning repeated-failure metadata and `replan_decision` trace
  fields for consecutive identical action/error/observation failures.
- `dm-agent-trace diff` for offline comparison of two JSONL traces, including
  status changes, step/tool/replan deltas, action-sequence divergence,
  tool-usage deltas, plan changes, and final-answer changes.
- `docs/research-log/07-trace-diff.md` documenting the trace-diff design and
  the next trace-analysis bets.
- `docs/research-log/08-trace-analyzer.md` documenting the analyzer rules and
  why the output remains advisory.
- `docs/research-log/09-maintenance-realism.md` documenting the benchmark task
  design and hidden-test contract.
- `docs/research-log/10-benchmark-confidence.md` documenting the interval
  design and interpretation limits.
- `docs/research-log/11-self-consistency-uncertainty.md` documenting the
  selection-explainability metadata.
- `docs/research-log/12-repeated-failure-signals.md` documenting the
  loop-detection signal and why it does not change replanning decisions yet.

## [2.0.0] - 2026-05-08

### Added
- P6 release materials:
  `docs/research-log/06-final-writeup.md`,
  `docs/research-log/DISTRIBUTION_CHECKLIST.md`, and
  `docs/research-log/INTERVIEW_TALKING_POINTS.md`.
- README / README_EN final v2 status sections, including the explicit freeze
  caveat for real SWE-bench, Docker/Tier-2, and cross-model evaluations.
- Release hardening docs in `docs/release-v2.0.0.md`.
- Default-off benchmark plumbing flags for coding/maintenance runs:
  `--enable-rag`, `--rag-top-k`, `--rag-granularity`, `--rag-max-files`,
  `--enable-critic`, `--self-consistency-runs`, and
  `--self-consistency-strategy`.
- Fresh-workspace self-consistency selection for coding/maintenance benchmark
  runs, with SWE-bench Lite self-consistency explicitly blocked while real
  SWE-bench evaluation is frozen.
- P5 Adaptive Replanning + Token Economics:
  `AdaptiveReplanPolicy`, `ReplanSignal`, and `ReplanDecision` classify
  `tool_error`, `parse_error`, `test_failure`, `critic_rejected`, and
  `max_steps` into deterministic replan strategies.
- `ReactAgent(enable_adaptive_replanning=True, max_replans=N)` opt-in strategy
  metadata plus `replan_decision` trace events. Existing replan behavior remains
  unchanged by default.
- `dm_agent/benchmarks/economics.py` and the `dm-agent-economics` CLI for
  offline pass-rate / token / cost-per-success reports from existing benchmark
  JSON files.
- Benchmark CLI fields: `--enable-adaptive-replanning`, `--max-replans`, and
  `--cost-per-1k-tokens`.
- `bench_reports/economics.json` and `bench_reports/economics.md` generated
  from the frozen P1 Tier-1 baseline without running new live evaluations.
- `docs/research-log/05-adaptive-and-economics.md` as the Phase 5 log.
- P4 Critic + Self-Consistency core:
  `dm_agent/core/critic.py` with `CriticAgent` / `CriticReview`, plus
  `dm_agent/core/self_consistency.py` with `SelfConsistencyRunner` and
  candidate summaries.
- `ReactAgent(critic=...)` opt-in completion gate, `critic_review` trace
  events, and critic pass/fail counters in run metadata.
- `tests/test_critic.py` and `tests/test_self_consistency.py` covering the
  keyless critic gate and the three selection strategies.
- `docs/research-log/04-critic-and-consistency.md` as the Phase 4 log.
- P3 RAG context retrieval:
  `dm_agent/memory/retriever.py` with `BM25Retriever`, optional
  `EmbeddingRetriever`, and `HybridRetriever` using Reciprocal Rank Fusion.
- `ReactAgent(enable_rag=True, retriever=...)` opt-in prompt injection of
  per-step `<retrieved_context>` blocks, plus `retrieval` trace events.
- `dm-agent-index` CLI for local index build/query workflows.
- `tests/test_retriever.py` and keyless Agent tests covering default-off RAG
  behavior and prompt injection.
- P2 Reflexion implementation scaffold:
  `dm_agent/core/reflexion.py` with `Reflector`, `EpisodicMemory`, and bounded
  lessons, plus default-off `ReactAgent(enable_reflexion=True, max_trials=N)`
  support for retrying failed trials.
- Trace events for Reflexion runs: `trial_start`, `trial_end`, and `reflexion`.
- `dm-agent-bench --enable-reflexion --max-trials N` options. SWE-bench Lite
  uses hidden-test verifier feedback between trials and reports `pass_at_1`,
  `pass_at_k`, and `avg_trials`.
- `tests/test_reflexion.py` covering the keyless Reflexion flow.

### Docs
- Added the Phase 6 final write-up, distribution checklist, and interview
  talking points.
- Added `docs/research-log/05-adaptive-and-economics.md` as the Phase 5
  implementation log and documented that real cross-model SWE-bench economics
  remain frozen until an allowed live evaluation.
- Added `docs/research-log/04-critic-and-consistency.md` as the Phase 4 implementation log.
- Added `docs/research-log/03-rag.md` as the Phase 3 implementation log.
- Added `docs/research-log/02-reflexion.md` as the Phase 2 implementation log.

## [1.7.1] - P1 SWE-bench Lite baseline

### Added
- Published the first SWE-bench Lite DeepSeek Tier-1 baseline report:
  `bench_reports/swebench_lite_baseline.json` and
  `bench_reports/swebench_lite_baseline.md`. This is a harness/trace baseline,
  not a leaderboard-comparable score.
- SWE-bench Lite CLI resume/checkpoint support: `--resume` and
  `--resume-from-output` reuse completed instance results from an existing
  JSON report, while `--output` / `--markdown` are now checkpointed after each
  newly completed instance.
- DeepSeek API retry protection for transient HTTP/network failures, including
  intermittent `400`, `429`, and 5xx responses during long benchmark runs.
- Windows-safe subprocess output decoding for benchmark and SWE-bench Lite
  verifier runs, avoiding `gbk` decode crashes on UTF-8 pytest output.

### Benchmarks
- SWE-bench Lite fixed 50-instance Tier-1 subset
  (`subset_signature=30e25d14e380`):
  0/50 resolved (0.0%), 36/50 patches applied (72.0%), avg 47.14 steps,
  avg 483,885 estimated tokens, `resume.reused_results=8`.
- Failure-mode distribution from
  `summarize_failure_modes`: `regression=36`, `patch_not_produced=13`,
  `patch_apply_failed=1`. A gold-patch smoke audit confirmed Tier-1
  host-verifier environment noise (missing historical dependencies and pytest
  node-id drift), so Tier-2 Docker is required before publishing an official
  SWE-bench-equivalent number.

## [1.7.0] - P1 SWE-bench Lite harness

### Added
- `dm_agent/benchmarks/swebench_lite/` package providing the SWE-bench Lite
  adapter: dataset loader with deterministic 50-instance subset
  (`fixed_subset_50`, seed=42, repo-balanced), per-instance git workspace
  manager, Tier-1 host-Python verifier, runner glue around `ReactAgent`, and
  a failure-mode analyzer with 9 actionable categories.
- `dm-agent-bench --suite swebench_lite` CLI integration with
  `--instance-id`, `--max-instances`, `--use-docker`, `--snapshot-path`,
  `--instance-test-timeout` options.
- `[swebench]` and `[rag]` optional dependency extras in `pyproject.toml`.
- `tests/test_swebench_loader.py`: 14 deterministic tests covering JSONL
  round-trip, subset stability, failure-mode classification, and the lazy
  import boundary; runs without the `[swebench]` extra.
- `docs/research-log/01-swebench-baseline.md` documenting harness design,
  Tier-1/Tier-2 trade-offs, sampling strategy, hyperparameters, cost
  estimate, and open questions.

### Notes
- Tier-2 docker-based verification raises `NotImplementedError` for now;
  Tier-1 covers the host-Python path. See research log 01 for rationale.
- The first real baseline number lands once we run the 50-instance subset
  on DeepSeek; the README badge will update at that point.

## [1.6.0] - P0 governance and v2 kickoff

### Added
- `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, GitHub issue/PR templates for project governance.
- `docs/research-log/` directory tracking design decisions, ablations, and lessons learned for the v2 algorithm-track upgrade.

### Changed
- README hero rewrite (Chinese + English): Algorithm Highlights, comparison
  table vs Aider/OpenHands/SWE-agent/smolagents, Research Log link.
- CONTRIBUTING.md: skill / benchmark task contribution guides, Conventional
  Commit prefix conventions.
- Removed in-line "thinking" TODO comments in `dm_agent/core/agent.py` and `dm_agent/core/planner.py` to keep the public source professional.

### Roadmap (v2 algorithm track)
- Phase 1: SWE-bench Lite adapter and public baseline score.
- Phase 2: Reflexion (self-reflection) mechanism with episodic memory.
- Phase 3: Hybrid BM25 + embedding retrieval (RAG) for repository-scale context.
- Phase 4: Critic agent and self-consistency selection.
- Phase 5: Adaptive replanning by error signal and cross-model token economics.
- Phase 6: Full README rewrite, demo recording, and community distribution.

See `docs/research-log/00-kickoff.md` for the detailed plan.

## [1.5.0] - 2025

### Added
- ReAct agent loop with planner, replan, and context compression.
- Multi-LLM support: DeepSeek, OpenAI, Claude, Gemini, custom `base_url`.
- MCP integration with config loader, manager, and per-server tool listing.
- Skill system with built-in `python_expert`, `db_expert`, `frontend_dev` and JSON-defined custom skills.
- JSONL trace writer, trace viewer CLI, dry replay, and opt-in tool replay.
- Coding benchmark and maintenance benchmark suites with hidden tests and changed-file constraints.
- Deterministic eval runner that does not require API keys.
- Cross-platform CI on Ubuntu and Windows for Python 3.10/3.11/3.12.
- Run report Markdown writer with git workspace status before/after.

[Unreleased]: https://github.com/hwfengcs/DM-Code-Agent/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/hwfengcs/DM-Code-Agent/compare/v1.7.1...v2.0.0
[1.7.1]: https://github.com/hwfengcs/DM-Code-Agent/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/hwfengcs/DM-Code-Agent/releases/tag/v1.7.0
[1.6.0]: https://github.com/hwfengcs/DM-Code-Agent/releases/tag/v1.6.0
[1.5.0]: https://github.com/hwfengcs/DM-Code-Agent/releases/tag/v1.5.0
