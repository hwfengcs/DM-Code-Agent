# Changelog

All notable changes to DM-Code-Agent are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.7.1] - P1 SWE-bench Lite baseline

### Added
- Published the first SWE-bench Lite DeepSeek Tier-1 smoke baseline report:
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
- SWE-bench Lite fixed 50-instance Tier-1 smoke subset
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

[Unreleased]: https://github.com/hwfengcs/DM-Code-Agent/compare/v1.7.1...HEAD
[1.7.1]: https://github.com/hwfengcs/DM-Code-Agent/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/hwfengcs/DM-Code-Agent/releases/tag/v1.7.0
[1.6.0]: https://github.com/hwfengcs/DM-Code-Agent/releases/tag/v1.6.0
[1.5.0]: https://github.com/hwfengcs/DM-Code-Agent/releases/tag/v1.5.0
