# 11 — Self-consistency uncertainty metadata

## TL;DR

Self-consistency selection now records why a candidate was selected and how much disagreement was
present. The selected output is unchanged; the new metadata is explanatory only.

For each multi-candidate run, metadata includes vote distribution, selected support, support
fraction, selected score, margin to runner-up, tie detection, disagreement reason, and a
`high` / `medium` / `low` confidence label.

## Context

P4 added self-consistency strategies:

- `majority_vote`
- `critic_score`
- `test_pass`

Those strategies pick a candidate, but the previous metadata did not distinguish an obvious 3-0
agreement from a fragile 1-1-1 tie. That matters for agent research because the same selected
answer can represent very different reliability profiles.

## What Changed

- `dm_agent/core/self_consistency.py`
  - `SelfConsistencyResult` now includes `uncertainty`.
  - `SelfConsistencyRunner.run()` records vote distribution and confidence metadata.
- `dm_agent/benchmarks/runner.py`
  - Benchmark-level self-consistency metadata mirrors the same uncertainty shape.
- Tests cover:
  - 2-1 majority support.
  - all-different low-confidence ties.
  - benchmark `test_pass` selection uncertainty.

## Metadata Shape

```json
{
  "uncertainty": {
    "strategy": "majority_vote",
    "num_candidates": 3,
    "unique_votes": 2,
    "vote_distribution": {"alpha": 2, "beta": 1},
    "selected_vote_key": "alpha",
    "selected_support": 2,
    "support_fraction": 0.6666666667,
    "selected_score": 1.0,
    "margin_to_runner_up": 0.0,
    "tie_detected": false,
    "disagreement_reason": "candidate_outputs_disagree",
    "runner_confidence": "medium"
  }
}
```

## Why It Is Default-Safe

The change does not:

- enable self-consistency by default;
- change selection strategy semantics;
- add model calls;
- change benchmark scoring.

It only makes existing opt-in self-consistency runs more interpretable.

## Keyless Checks

```bash
python -m pytest tests/test_self_consistency.py tests/test_coding_benchmarks.py
python -m ruff check dm_agent/core/self_consistency.py dm_agent/benchmarks/runner.py tests/test_self_consistency.py tests/test_coding_benchmarks.py
python -m black --check dm_agent/core/self_consistency.py dm_agent/benchmarks/runner.py tests/test_self_consistency.py tests/test_coding_benchmarks.py
```

## Open Questions / Next Bets

- Add uncertainty-aware benchmark report rendering for self-consistency runs.
- Use patch-fingerprint voting metadata in benchmark Markdown summaries.
- Combine uncertainty metadata with trace analyzer output for "selected but risky" warnings.
