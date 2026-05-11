# 18 - Patch-fingerprint self-consistency voting

## TL;DR

Self-consistency can now compare file-edit candidates by a stable patch fingerprint instead of only
their final-answer text. The feature is still default-off because self-consistency itself is
default-off, and the fallback remains unchanged: if no patch fingerprint is present, voting uses the
final answer.

## Context

The first self-consistency implementation grouped candidates by `final_answer`. That is useful for
answer-only tasks, but weak for code maintenance. Two candidates can produce the same patch while
wording their final message differently, or produce different patches while ending with the same
generic "done" answer.

For maintenance benchmarks, the edited workspace is the artifact that matters. The vote key should
prefer the changed files when that information is available.

## What Changed

- `dm_agent/core/self_consistency.py`
  - candidate summaries now include `vote_key_source` and optional `patch_fingerprint`.
  - vote-key normalization uses `metadata.patch_fingerprint` first, then falls back to
    `final_answer`, then `metadata.prediction`.
- `dm_agent/benchmarks/runner.py`
  - benchmark runs compute `metadata.patch_fingerprint` after agent edits and before hidden tests
    are injected.
  - benchmark self-consistency majority vote and uncertainty metadata use that fingerprint when it
    exists.
  - candidate summaries expose `vote_key`, `vote_key_source`, and `patch_fingerprint`.

The fingerprint is a short stable hash of changed tracked paths plus before/after content hashes.
It does not include full patch contents and it is computed before hidden tests are written.

## Why It Is Default-Safe

This change does not enable self-consistency by default, add model calls, or alter benchmark scoring.
It only changes how an already opt-in multi-candidate run groups candidates when patch metadata is
present. Runs without patch metadata preserve the previous final-answer voting behavior.

## Keyless Checks

```bash
python -m pytest tests/test_self_consistency.py tests/test_coding_benchmarks.py
python -m ruff check dm_agent/core/self_consistency.py dm_agent/benchmarks/runner.py tests/test_self_consistency.py tests/test_coding_benchmarks.py
python -m black --check dm_agent/core/self_consistency.py dm_agent/benchmarks/runner.py tests/test_self_consistency.py tests/test_coding_benchmarks.py
```

## Open Questions / Next Bets

- Render patch-vote metadata in benchmark Markdown without exposing full patches.
- Add a manifest diff CLI so benchmark reports cannot be casually compared across different task
  sets.
- Combine patch-vote disagreement with trace-analysis health grades for reviewer-facing risk flags.
