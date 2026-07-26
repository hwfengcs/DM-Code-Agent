# 25 — Unified LLM retry and atomic file I/O

## TL;DR

Three default-on resilience fixes in the state-management track:

1. **Unified retryable LLM error handling** — previously only DeepSeek had
   retries; a transient timeout/429/5xx on Claude/OpenAI/Gemini propagated
   through `ReactAgent._run_once` and killed the whole run. Now `LLMError`
   carries a `retryable` flag, `BaseLLMClient.complete_with_retry` retries
   only retryable failures with exponential backoff
   (`--llm-max-retries`, default 2), and all three SDK clients classify
   their exceptions via a provider-agnostic `classify_retryable_exception`.
2. **Atomic file writes + per-run backups** — `create_file`/`edit_file` write
   via same-directory temp file + `os.replace` (Windows-safe, one
   PermissionError retry, non-atomic fallback annotated in the observation).
   Before each write-class tool call the agent copies the original file to
   `{tempdir}/dm_agent_backups/{run_id}/{step:03d}-{name}` and reports the
   backup dir at run end (`file_backup` trace event).
3. **MCP timeout + single reconnect** — the hardcoded 5s JSON-RPC timeout is
   now per-server configurable (`"timeout"` in `mcp_config.json`), and the
   tool wrapper attempts one reconnect when the server process has died,
   instead of returning error strings forever.

## Design decisions

- **DeepSeek double-retry avoidance.** `DeepSeekClient` keeps its internal
  status-code-aware loop and passes `respond_retries=0` to the base class,
  so its `DeepSeekError` (raised after the internal budget is spent) is never
  retried again. The base parameter is named `respond_retries` /
  `respond_retry_backoff` precisely to avoid colliding with DeepSeek's
  existing `max_retries` / `retry_backoff` attributes.
- **`UsageTrackingClient` bypass fix.** The benchmark/real-eval wrapper's
  `respond` called `self.complete → inner.complete` directly, skipping any
  base-class retry. Its `complete` now routes through
  `complete_with_retry` when the inner client provides it (one line), so
  benchmark runs get the same resilience.
- **Retry observability.** Clients have no trace writer, so retries surface
  as a counter: agents report `metadata["llm_retry_count"]` per run (delta of
  the client's `total_respond_retries`). A per-attempt trace event would
  require threading the writer into every client — deferred until a need
  shows up.
- **Backups live outside the workspace.** In-workspace backups would pollute
  the benchmark changed-files audit (`_should_track_file`) and SWE-bench git
  diffs. Restore is intentionally manual (copy back from the printed dir);
  an automatic rollback tool is out of scope until there is evidence it is
  needed.
- **Classification is best-effort.** `classify_retryable_exception` checks
  `status_code`/`code` attributes against {408, 409, 429, 5xx}, then
  exception-type-name tokens, then message text. Semantic 4xx (401/404/422)
  never retry.

## Measurement

Keyless: `tests/test_llm_retry.py` (retry-until-success, non-retryable
passthrough, budget exhaustion, wrapper routing, classifier table),
`tests/test_tools.py` (atomic write, no temp residue),
`tests/test_agent_guards.py` (backup copy created with original content),
`tests/test_skills_and_mcp.py` (timeout config round-trip, stubbed reconnect
success/failure). `tests/test_deepseek_client.py` is untouched and still
passes — the internal loop semantics did not change.

## Open questions / next bets

1. Respect provider `Retry-After` headers instead of pure exponential backoff.
2. Backup dirs accumulate in the system temp dir; an age-based sweeper (or
   reusing the OS temp cleanup) may be worth a follow-up.
3. MCP reconnect is single-shot per call; a health-check loop is deliberately
   out of scope.
