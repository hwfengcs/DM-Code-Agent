# 02 — Reflexion: episodic memory across failed trials

> **TL;DR.** Phase 2 now has the core Reflexion mechanism: failed trials can
> produce a concise lesson, store it in bounded episodic memory, and inject it
> into the next attempt. The feature is default-off. This entry records the
> implementation landing; the SWE-bench Lite ablation is intentionally pending
> because the P1 Tier-1 verifier has known noise.

## Context

P1 produced useful traces and failure categories, but it also showed a common
agent failure pattern: long runs that either never produced a patch or produced
a broad patch without using the concrete failure signal. Reflexion targets that
class of error by making failed attempts explicit training data for the next
attempt.

This implementation follows the prompt-based shape of Shinn et al.'s Reflexion:

1. Run a trial.
2. If it fails, summarize what went wrong into one actionable lesson.
3. Store the lesson in episodic memory.
4. Start a fresh trial with the lesson injected into the prompt.

There is no RL and no persistent global memory. Lessons are per-run, bounded,
and auditable in trace metadata.

## Implementation

New module:

```text
dm_agent/core/reflexion.py
├── Lesson
├── EpisodicMemory
└── Reflector
```

`ReactAgent` now accepts:

| Parameter | Default | Meaning |
| --- | ---: | --- |
| `enable_reflexion` | `False` | Keep existing behavior unless explicitly enabled. |
| `max_trials` | `3` | Maximum internal trials for agent-level failures. |
| `reflector` | `None` | Optional custom reflector; defaults to same LLM client. |
| `reflexion_memory` | `None` | Optional pre-seeded episodic memory. |

Trace events added:

- `trial_start`
- `trial_end`
- `reflexion`

SWE-bench Lite runner now has a separate hidden-test feedback loop:

```bash
dm-agent-bench --suite swebench_lite \
  --provider deepseek \
  --enable-reflexion \
  --max-trials 3 \
  --max-instances 5
```

The runner keeps P1 default behavior unchanged. When enabled, it retries only
after verifier failure, stores hidden-test feedback as a lesson, and reports
`pass_at_1`, `pass_at_k`, and `avg_trials`.

## Current validation

Keyless tests cover:

- bounded episodic memory rendering;
- reflector prompt/lesson normalization;
- `ReactAgent` trial 1 failure → reflection → trial 2 prompt injection;
- SWE-bench runner hidden-test failure → lesson → second trial.

No live-model ablation is published in this entry. That is deliberate: P1's
Tier-1 host verifier is noisy enough that a public P2 number should wait until
we either choose a clean deterministic subset or add Tier-2 Docker verification.

## Next bets

1. Run a small keyhole ablation on a manually inspected 5-10 instance subset
   where Tier-1 verifier noise is low.
2. Decide whether Reflexion should trigger after `patch_not_produced` only, or
   also after broad `regression` failures.
3. Add report rendering for per-trial lessons once the first live ablation
   produces data worth publishing.
