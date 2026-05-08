# Interview talking points

Private prep notes for discussing DM-Code-Agent as an AI agent engineering project.

1. Built local-first ReAct code agent with JSONL trace/replay and hidden-test benchmarks.
2. Added SWE-bench Lite Tier-1 harness and published frozen 50-instance baseline.
3. Implemented default-off Reflexion, RAG, Critic, and Self-Consistency modules.
4. Added deterministic adaptive replanning by error signal with traceable decisions.
5. Built offline token economics reports from benchmark JSON without live API calls.
6. Extended trace tooling with offline diff/analyze and added multi-file maintenance benchmarks
   that require code, docs, and regression-test changes.
7. Added Wilson confidence intervals to benchmark summaries so ablation reports expose uncertainty
   instead of only point estimates.
8. Added self-consistency uncertainty metadata so multi-candidate selection reports disagreement,
   support, and confidence without changing the selected output.

Use the caveat explicitly: current SWE-bench Lite number is Tier-1 host-verifier only and not
leaderboard-comparable. Do not claim real score improvements for v2 mechanisms until a permitted
live ablation has been run.
