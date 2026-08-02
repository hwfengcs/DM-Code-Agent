# Changelog

All notable changes to DM-Code-Agent are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Installability: user-level config and `.env` (2026-08)

Three bugs that made `pip install dm-code-agent` unusable outside a cloned repo. All three
were **invisible under editable installs**, where "relative to the package" and "relative to
the working directory" happen to coincide. Details and rejected alternatives in
[`docs/research-log/32-user-level-config-and-env.md`](docs/research-log/32-user-level-config-and-env.md).

#### Changed (breaking)
- **`config.json` lookup is now `./config.json` → `~/.dm_agent/config.json`.** Previously the
  path was `Path(__file__).parents[2] / "config.json"`, which resolves to `site-packages/`
  once the package is actually installed — polluting the install root, failing outright on
  read-only or system Python installs, sharing one config across every project, and leaving
  the file somewhere the user cannot find. Saves write back to **whichever file was read**,
  falling back to user level. Running from a cloned repo is byte-for-byte unchanged, so no
  migration is required.
- **`dm_agent.cli.CONFIG_FILE` removed** from the public `__all__`. Its semantics were wrong
  and keeping it would invite the same bug. Use `dm_agent.paths.resolve_config_read_path()` /
  `resolve_config_write_path()`.

#### Fixed
- **The user's `.env` is found again.** Bare `load_dotenv()` calls `find_dotenv(usecwd=False)`,
  which searches upward from the *calling module's* directory — installed, that walk starts in
  `site-packages/dm_agent/cli/` and never reaches the user's project, so a `.env` next to their
  code silently did nothing. Now loaded explicitly as `./.env` → `~/.dm_agent/.env`, keeping
  dotenv's `override=False` so **exported environment variables still win over both files**.
- **`.env` files with a UTF-8 BOM now work.** Found while verifying the fix above from a real
  install: dotenv reads as plain `utf-8` and folds the BOM into the first key name
  (`﻿DEEPSEEK_API_KEY`), so the key is set but unreadable and the error still says
  "missing API key" — undiagnosable in practice. Every common way to create a `.env` on
  Windows writes a BOM (`Set-Content -Encoding utf8`, `>` redirection, Notepad's "UTF-8"),
  so files are now read as `utf-8-sig`, which is identical to `utf-8` when no BOM is present.
- **Missing-key errors are actionable.** The message now prints resolved absolute paths for all
  three options (environment variable, `~/.dm_agent/.env`, `./.env`) plus the provider's key
  console URL, instead of "set an environment variable" with no indication of where.
- The welcome screen prints the config file's full path rather than the bare name `config.json`,
  which after a global install says nothing about which of the two files was read.

#### Added
- **`dm_agent/paths.py`** — dependency-free path resolution shared by `cli` and `server`
  (`server` may not import `cli`; it spawns it). Includes atomic JSON writes and POSIX
  permission tightening for config files.
- **`tests/test_cli_config_paths.py`** (15 cases), including a regression guard asserting that
  no resolved config path ever lands inside the package directory.
- **`isolate_user_home` autouse fixture** redirecting `HOME` and `USERPROFILE` (Windows
  `Path.home()` reads the latter) into a temp dir. Without it, `parse_args()` now reaches
  `~/.dm_agent/config.json` and every test's behaviour would depend on whether the machine
  running it happens to have that file.

### Web console (2026-07)

A browser UI (`dm-agent-web`) serving two purposes with **one renderer**: a local
workbench (start tasks, watch steps live, fork from any entry) and a read-only gallery
(auditable session viewer needing no API key, hostable as static files). Live runs and
historical traces are the same append-only JSONL entry stream, so "what you watch" and
"what you audit afterwards" cannot diverge.

#### Added
- **`dm_agent/server/`** — a second outermost assembler, sibling to `dm_agent/cli/`:
  read-only audit API, subprocess executor, SSE streaming. Optional `[web]` extra; the
  core package stays free of web framework dependencies.
- **Read-only endpoints** reusing `dm_agent.tracing` pure functions verbatim
  (`summarize_events` / `analyze_events` / `diff_events` / `fork_session`), so the console
  and `dm-agent-trace` always reach the same conclusions — pinned by a field-by-field
  comparison test rather than by convention.
- **`POST /api/runs`** spawns a `python -m dm_agent.cli` subprocess. Chosen over
  in-process `ReactAgent` because the kernel has no cancellation interface (a hook raising
  is documented as equivalent to allowing), and because it makes the web UI a *frontend to
  the CLI* rather than a second assembly path that could drift.
- **SSE live stream** tailing the session log itself (`TraceWriter` flushes per entry).
  `id:` is the line number; append-only guarantees line numbers never shift, so the
  browser's `Last-Event-ID` resumption works without server-side bookkeeping.
- **`web/`** — React 19 + Vite + Tailwind v4 frontend, built into
  `dm_agent/server/static/` and committed so `pip install dm-code-agent[web]` ships a
  working UI without requiring Node. CI rebuilds and diffs the artifacts.
- **`dm_agent/cli/__main__.py`** (3 lines), fixing the long-standing "`python -m
  dm_agent.cli` silently does nothing" pitfall recorded in CLAUDE.md.

#### Fixed
- Run status no longer equates exit code 0 with success. `dm-agent` returns 0 for
  `max_steps_exceeded` (not a CLI failure, just an unfinished agent), which the console
  initially reported as `completed`. It now also reads the agent's own verdict from the
  session log's `run_end`, adding an `incomplete` state. Caught by end-to-end manual
  verification, not by the test suite — which is why the regression test exists now.
- SPA deep links returned a JSON 404: `StaticFiles.get_response` *raises*
  `HTTPException` rather than returning a 404 response, and raises **starlette's** class,
  of which FastAPI's same-named class is a subclass — so `except fastapi.HTTPException`
  never caught it.
- The startup banner (carrying the only clickable token URL) vanished whenever stdout was
  redirected: `print()` is block-buffered on a pipe and `uvicorn.run()` never returns.
  Now flushed explicitly, and encoded as UTF-8 so Chinese text survives Windows
  redirection instead of being mangled by cp936.

#### Testing
- 66 new cases across five files, all offline: layering invariants (AST-asserted, because
  `dm_agent/server/**` must be exempt from `TID251` to allow `from .settings import`),
  security model, argv whitelisting fed to the *real* CLI parser, SSE semantics
  (partial lines, resumption, trailing entries after process exit), and run lifecycle.
- **`tests/conftest.py` now forces a dummy API key on every test.** The project
  constitution requires tests to run without keys; while writing the run-lifecycle tests
  the first version relied on "no key configured, so the CLI fails fast" — and really
  spent money. `load_dotenv()`'s `find_dotenv()` searches upward from the *calling
  module's* directory (`dm_agent/cli/`), so a subprocess picks up the repo-root `.env`
  regardless of its cwd; and on Windows `os.environ[k] = ""` deletes the variable, letting
  dotenv refill the real key. This is now a machine guarantee instead of something to
  remember.

### Architecture refactor (2026-07, eight steps)

An eight-step restructuring benchmarked against
[Pi Agent Harness](https://github.com/earendil-works/pi-mono). Every step was required to
keep `python -m dm_agent.evals.cli` **identical field by field** to the pre-refactor
baseline; the four default-off paths (Reflexion / Critic / circuit breaker /
breaker×guard) were A/B-compared with a dedicated probe script on top of that.

#### Added
- **Lifecycle event bus** (`dm_agent/core/events.py`) with six interceptable hooks:
  `before_tool_call` (rewrite arguments in place, or `{"block": True, "reason": ...}`),
  `after_tool_result` (middleware-style observation rewriting), `before_llm_request`
  (rewrite messages, carries a `phase`), `before_finish` (veto a completion),
  `on_run_start` (mutate metadata, append to the system prompt), and `on_run_end`
  (`{"retry": True}` to discard the attempt and rerun). Handlers run in registration order;
  an exception in one handler is isolated, logged as a `hook_error` entry, and does not
  abort the run.
- **Extension system** (`dm_agent/extensions/`): `ExtensionAPI` with `register_tool` /
  `register_skill` / `register_provider` / `on`, plus three discovery sources in ascending
  priority — built-ins, `dm_agent.extensions` entry points, `~/.dm_agent/extensions/*.py`,
  project-local `.dm_agent/extensions/*.py`, and `--extension PATH`. Adding a tool, skill,
  provider, or guard now requires **zero changes under `dm_agent/`**.
- **Project trust model**: project-local extensions are never imported without explicit
  authorization. Decisions are stored outside the repository in
  `~/.dm_agent/trusted-projects.json`; non-interactive environments skip untrusted projects
  instead of blocking. New `--no-extensions` and `--extension` flags (mutually exclusive).
- **Session tree**: every JSONL entry now carries `id` (`<run-id-prefix>-<seq>`) and
  `parent_id`, making the run history a navigable tree (schema `1.2` → `2.0`, purely
  additive — `event`/`payload` keys unchanged). New entry types: `message`, `compaction`,
  `checkpoint`, `fork`.
- **Non-destructive context compaction**: folding now appends a `compaction` entry
  (`first_kept_entry_id`, `folded_entry_ids`, summary, token estimates) and the request's
  message list is assembled by *skipping* the folded range. **No original entry is ever
  deleted.** `tracing.session.rebuild_context(entries, apply_compaction=False)` replays the
  same session as if compaction never happened — the difference is exactly what was folded,
  which makes the `no_compression` ablation attributable instead of just two end-to-end
  scores. The messages sent to the model are byte-identical to before.
- **`dm-agent-trace fork <session.jsonl> --at <entry-id>`**: branch a new session from any
  entry. Entries up to the fork point are copied verbatim and a `fork` entry whose
  `parent_id` points back at the fork point is appended.
- **`--checkpoint *.jsonl`**: append-only session-format checkpointing (every step's snapshot
  is kept) with `--resume-at <entry-id>` to resume from an earlier entry. `--checkpoint`
  with any other suffix keeps the original single-file JSON snapshot, and `--resume` sniffs
  both formats, so existing usage is unchanged.
- **`uv.lock`** for reproducible installs; CI now runs `uv sync --frozen --extra dev` and
  fails on `uv lock --check`.
- **mypy** over `dm_agent`, with `disallow_untyped_defs` enforced for `dm_agent.tools.*` and
  `dm_agent.clients.*`.
- **Layering contract** enforced by ruff `TID251`: `core` / `tools` / `clients` / `memory` /
  `tracing` / `evals` / `benchmarks` may not import `dm_agent.cli`.

#### Changed
- **`main.py` moved into the package.** `dm-agent` now points at `dm_agent.cli:main` and
  `py-modules = ["main"]` is gone — installing the project no longer puts a top-level `main`
  module into `site-packages`. The root `main.py` is a thin shim for `python main.py`.
- **Ruff rule set widened** from `E9 F63 F7 F82` to `E F I UP B SIM TID RUF`, with `E501` and
  `RUF001`–`RUF003` disabled on purpose (rationale in `pyproject.toml`). No `# noqa` in
  source files.
- **LLM providers, built-in tools, and built-in skills are now registered** through the same
  `ExtensionAPI` third parties use, rather than hard-coded lists.
- **Optional capabilities moved out of the kernel.** Critic, circuit breaker, Reflexion, and
  the read-before-edit guard are now event handlers under
  `dm_agent/extensions/capabilities/` (and `core/guards.py`). The `--enable-*` flags are kept
  as a transitional surface and are internally equivalent to loading the matching capability;
  behavior and eval output are unchanged.
- **`dm_agent/core/agent.py` split** from 1616 to 866 lines. Per-step concerns became sibling
  modules: `run_state`, `prompting`, `context_window`, `response_parser`, `tool_invoker`,
  `observation`, `completion`, `replan`, `persistence`. `ReactAgent` is down to 4 public
  methods.
- **Documentation restructured.** `README.md` 19.6 KB → 2.7 KB navigation page; content split
  into `docs/getting-started.md`, `docs/cli.md`, `docs/capabilities.md`,
  `docs/project-status.md`, and a `docs/README.md` index. `MCP_GUIDE.md` → `docs/mcp.md`,
  `SKILL_GUIDE.md` → `docs/skills.md`. New `docs/architecture.md` (prose/mermaid, now the
  authoritative source over the drawio/png) and a rewritten `docs/extensions.md` with an API
  reference, the security model, and three verified runnable examples.

#### Removed
- `README_FR.md`. Measured at 1,955 characters versus the Chinese README's 14,324, with 5
  sections against 19 and no French accents anywhere, it had never actually been maintained.
  `README_EN.md` is kept and synchronized with the slimmed structure; pages under `docs/`
  are Chinese-only, stated explicitly in both READMEs.

#### Notes
- No evaluation claims changed. Real SWE-bench / Docker / cross-model scoring remains frozen.
- Devlogs: [`docs/research-log/29-session-tree.md`](docs/research-log/29-session-tree.md)
  covers the session tree and non-destructive compaction.

### Added
- Default-on observation truncation: tool outputs beyond
  `--max-observation-chars` (default 8000) keep head+tail with an explicit
  `[truncated: ...]` marker and concrete `read_file` paging hints; audited via
  the `observation_truncated` trace event and `truncation_count` metadata.
- Token-budget compression trigger: `--context-token-budget` (default 24000
  estimated tokens, chars/4 heuristic) forces early local compression when the
  pending history grows too large; audited via `context_budget` trace events.
- Default-on read-before-edit guard: `edit_file` is blocked until the target
  file was read this run (and re-read after any write). Opt out with
  `--disable-edit-guard`; audited via `edit_guard` trace events.
- `--enable-memory-hygiene` (default off): success observations supersede
  matching failure memories (importance/score down-weighting plus a staleness
  note when rendered) and recall queries are anchored to the task text.
- `--enable-llm-compression` (default off): folding old context additionally
  stores one LLM-written summary memory, with silent fallback to the
  rule-based path on any client failure.
- Trace schema 1.1 (additive): new events `observation_truncated`,
  `context_budget`, `edit_guard`, `memory_invalidation`, and an
  `estimated_prompt_tokens` field on `llm_call`.
- Unified retryable LLM error handling: `--llm-max-retries` (default 2)
  retries transient timeouts/429/5xx with exponential backoff for all four
  providers (DeepSeek keeps its internal loop; benchmark usage wrapper now
  routes through the retry layer too).
- Atomic file writes for `create_file`/`edit_file` (temp file + `os.replace`,
  Windows-safe fallback) and per-run pre-write backups under the system temp
  directory, reported at run end and via `file_backup` trace events.
- Configurable MCP request timeout (`"timeout"` per server in
  `mcp_config.json`) and a single automatic reconnect when a server process
  dies mid-run.
- Run-level checkpoint/resume: `--checkpoint` snapshots conversation, steps,
  metadata, plan, and local memories after every step; `--resume` continues
  from the snapshot (task argument optional). Max-steps runs write a terminal
  snapshot resumable with a larger `--max-steps`.
- Progress-carrying replan: regenerated plans keep completed steps with
  continued numbering, plan progress is matched against the next pending step
  only, and the default (non-adaptive) replan path gains a budget of 5
  (`--max-replans` overrides).
- `--reflexion-memory-file` to persist Reflexion lessons across runs.
- `--enable-circuit-breaker` (default off): temporarily disables a tool after
  N consecutive same-kind failures with cooldown and probe recovery, audited
  via `circuit_breaker` trace events.
- Recovery success rate (`recovered_runs / runs_with_failures`) and per-tag
  capability breakdowns in eval and benchmark summaries and reports;
  trace directory analysis aggregates the same rate.
- Hallucination proxy signals in `dm-agent-trace analyze`/`analyze-dir`:
  edits without a prior read, edit-guard blocks, truncated observations, and
  missing-path references (advisory; not part of the trace-health score).
- Repeat-variance stability metrics for `dm-agent-bench --repeat`: per-task
  pass@k, pass^k, and task pass-rate stddev.
- `dm-agent-bench --per-test-credit`: advisory node-by-node hidden-test
  partial credit (strict scoring unchanged) and `--manifest-only` for keyless
  manifest generation.
- CI quality gates: the full keyless eval suite must stay at 100%
  (`dm_agent/evals/gate.py`) and benchmark manifests are diffed against
  checked-in baselines so task drift fails the build.
- New keyless eval tasks `truncated_read_pagination` and `edit_guard_reread`
  driven by the new `EvalTask.agent_overrides` mechanism.

### Fixed
- SWE-bench Lite failure-mode analyzer now recognizes the agent's actual
  `max_steps_exceeded` terminal status (plus the `agent_status_max_steps*`
  failure-reason fallback), so step-budget failures are no longer
  miscategorized as `regression`. Frozen resolved/patch-applied numbers are
  unaffected; see the errata in `docs/research-log/01-swebench-baseline.md`.

### Removed
- Legacy repository-index context support, including its CLI entry point,
  old context exports, agent opt-in flags, benchmark flags, and the optional
  dependency extra.

### Added
- Mem0-style local context memory: older conversation turns are stored as
  scoped atomic memories and only relevant memories are injected back into the
  prompt.
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
- Benchmark report `manifest` provenance with hidden-contract task
  fingerprints, variant names, and suite signature.
- Compact per-run `trace_analysis` metadata in coding/maintenance benchmark
  reports when `--trace-dir` is enabled.
- `dm-agent-trace analyze-dir` for offline aggregation of trace-health,
  verification-gap, and failure-stage counts across trace directories.
- `dm-agent-economics` now carries pass-rate 95% confidence intervals from
  benchmark reports, with a Wilson fallback for older reports.
- `dm-agent-trace diff` for offline comparison of two JSONL traces, including
  status changes, step/tool/replan deltas, action-sequence divergence,
  tool-usage deltas, plan changes, and final-answer changes.
- `packaging_ci_contract`, a multi-file maintenance benchmark task that repairs
  Python packaging metadata, dev extras, CI matrix/install commands, CI checks,
  and regression coverage under deterministic hidden tests.
- Patch-fingerprint voting for self-consistency: benchmark candidates now carry
  a stable workspace-local patch fingerprint, and core/benchmark selection uses
  it when present before falling back to final-answer text.
- `dm-agent-manifest-diff`, an offline CLI for comparing two benchmark report
  manifests before score comparisons. It highlights suite-signature, task
  fingerprint, and variant-name drift without rerunning benchmarks.
- `dm-agent-economics` manifest guard metadata and Markdown warning when input
  reports carry different benchmark suite signatures.
- `dm-agent-trace analyze-dir --markdown PATH` for shareable trace-health
  summaries that avoid raw prompt, observation, tool-output, and final-answer
  contents.
- Default-off repeated-failure policy experiment for adaptive replanning. When
  explicitly enabled, repeated action/error signatures can select a
  loop-breaking replan strategy without changing default behavior.
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
- `docs/research-log/13-benchmark-provenance.md` documenting task
  fingerprints and suite signatures.
- `docs/research-log/14-benchmark-trace-analysis.md` documenting trace
  analyzer integration in benchmark reports.
- `docs/research-log/15-trace-analysis-aggregation.md` documenting directory
  aggregation for trace review.
- `docs/research-log/16-economics-uncertainty.md` documenting confidence-aware
  offline economics reporting.
- `docs/research-log/17-packaging-ci-maintenance.md` documenting the
  packaging/CI maintenance benchmark contract.
- `docs/research-log/18-self-consistency-patch-fingerprint.md` documenting
  patch-based self-consistency voting.
- `docs/research-log/19-benchmark-manifest-diff.md` documenting manifest diff
  guardrails for benchmark comparisons.
- `docs/research-log/20-economics-manifest-guard.md` documenting
  suite-signature warnings in economics reports.
- `docs/research-log/21-trace-analysis-markdown.md` documenting the
  trace-directory Markdown report and privacy boundary.
- `docs/research-log/22-repeated-failure-policy-experiment.md` documenting the
  default-off repeated-failure policy experiment.

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
- `[swebench]` optional dependency extra in `pyproject.toml`.
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
- Phase 3: scoped context memory for repository-scale agent runs.
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
