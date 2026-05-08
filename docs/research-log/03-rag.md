# 03 — RAG-based context retrieval

## TL;DR

P3 lands the minimum usable RAG layer: `BM25Retriever`, optional `EmbeddingRetriever`, and
`HybridRetriever` with Reciprocal Rank Fusion. It is default-off. Normal `ReactAgent` behavior is
unchanged unless callers pass `enable_rag=True` and a retriever instance.

The implementation is deliberately conservative: BM25 has a tiny built-in fallback so keyless tests
do not need `rank-bm25`; `sentence-transformers` is still optional behind `[rag]`; embeddings can be
tested with an injected encoder. SWE-bench Lite Docker/Tier-2 and the P1 baseline are frozen for now,
so this entry records implementation smoke tests rather than a real pass-rate ablation.

## Context

The baseline ReAct loop can inspect files with tools, but large repositories create a practical
context problem: the model needs a hint about where to look before it spends steps searching. P3 adds
retrieval as a prompt-time hint, not as an authority. The prompt explicitly says to use retrieved
context only if relevant and to prefer direct tool inspection before editing.

## What Changed

- `dm_agent/memory/retriever.py`
  - `RetrievalDocument` and `RetrievalResult` data models.
  - Python repository indexing at `symbol`, `file`, or `both` granularity.
  - `BM25Retriever` using `rank-bm25` when installed and a lightweight fallback otherwise.
  - `EmbeddingRetriever` using optional `sentence-transformers` or an injected encoder.
  - `HybridRetriever` with RRF fusion.
  - Optional persisted document cache at `.dm-agent-cache/index/documents.json`, invalidated by
    file mtime/size.
- `dm_agent/memory/index_cli.py`
  - `dm-agent-index build --root . --persist`
  - `dm-agent-index query "..." --top-k 5`
- `ReactAgent`
  - New `enable_rag=False`, `retriever=None`, `rag_top_k=5` parameters.
  - Per-step retrieval query = task + last 3 observations.
  - Retrieved snippets are injected into the system prompt as `<retrieved_context>`.
  - Trace event: `retrieval` records query, doc ids, scores, source, and rank.

## Design Notes

BM25 is the default path because it is cheap, deterministic, and often enough for stack traces,
symbol names, test names, and exact error strings. Embeddings are useful for "find similar behavior"
queries, but the dependency is heavy, so it stays optional.

Hybrid retrieval uses Reciprocal Rank Fusion rather than score normalization. BM25 scores and cosine
similarities live on different scales; RRF keeps the fusion stable and easy to reason about.

Symbol granularity is the default because it keeps prompt snippets small. File-level indexing is
still available for modules where top-level symbols do not capture the useful context.

## Keyless Checks

Implemented tests avoid real LLMs and external services:

```bash
python -m pytest tests/test_retriever.py tests/test_planner_agent.py
python -m dm_agent.memory.index_cli build --root . --max-files 5 --no-tests
```

Current smoke result during implementation: `18 passed`.

## Ablation Status

Planned matrix once the verifier track is unfrozen:

| Config | Retriever | Embeddings | Expected cost | Status |
| --- | --- | --- | --- | --- |
| no_rag | none | no | baseline | pending |
| bm25_only | BM25 | no | low | pending |
| embedding_only | embeddings | yes | medium local CPU cost | pending |
| hybrid | BM25 + embeddings + RRF | yes | medium | pending |

We are not changing the P1 SWE-bench Lite baseline or running Docker/Tier-2 in this phase pass.

## Open Questions / Next Bets

- Whether retrieval should run every ReAct step or only after errors/search failures.
- Whether symbol snippets need surrounding context lines.
- Whether persisted embedding vectors are worth the cache complexity.
- Whether RAG should be wired into benchmark variants first, before the public CLI exposes a flag.
