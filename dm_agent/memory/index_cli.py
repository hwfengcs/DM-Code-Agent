"""CLI for building and querying local retrieval indexes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .retriever import (
    BM25Retriever,
    DEFAULT_MAX_FILES,
    DEFAULT_TOP_K,
    EmbeddingRetriever,
    HybridRetriever,
    build_repository_documents,
    default_cache_path,
    format_retrieved_context,
    save_documents,
)


def parse_args(argv: Any = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or query a DM-Code-Agent RAG index.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a retrieval index for a repository.")
    build.add_argument("--root", default=".", help="Repository root to index.")
    build.add_argument(
        "--granularity",
        choices=["symbol", "file", "both"],
        default="symbol",
        help="Index chunk granularity.",
    )
    build.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    build.add_argument("--no-tests", action="store_true", help="Exclude tests from the index.")
    build.add_argument(
        "--persist",
        action="store_true",
        help="Write the index to .dm-agent-cache/index/documents.json.",
    )
    build.add_argument("--output", type=Path, help="Write the index JSON to this path.")

    query = subparsers.add_parser("query", help="Query a retrieval index.")
    query.add_argument("query", help="Query text.")
    query.add_argument("--root", default=".", help="Repository root to index.")
    query.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    query.add_argument(
        "--granularity",
        choices=["symbol", "file", "both"],
        default="symbol",
        help="Index chunk granularity.",
    )
    query.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    query.add_argument("--no-tests", action="store_true", help="Exclude tests from the index.")
    query.add_argument(
        "--mode",
        choices=["bm25", "embedding", "hybrid"],
        default="bm25",
        help="Retriever backend. Embedding/hybrid require the [rag] extra unless an encoder is injected in code.",
    )
    query.add_argument(
        "--embeddings",
        action="store_true",
        help="Include the embedding backend when --mode hybrid is used.",
    )
    query.add_argument(
        "--persist",
        action="store_true",
        help="Use .dm-agent-cache/index/documents.json when mtimes match.",
    )
    query.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON instead of a prompt-ready context block.",
    )

    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "build":
            return _build(args)
        if args.command == "query":
            return _query(args)
    except (RuntimeError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 2


def _build(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    documents = build_repository_documents(
        root,
        granularity=args.granularity,
        max_files=args.max_files,
        include_tests=not args.no_tests,
    )
    output = args.output
    if args.persist:
        output = default_cache_path(root)
    if output:
        save_documents(documents, output, root=root, granularity=args.granularity)

    payload = {
        "root": str(root),
        "document_count": len(documents),
        "granularity": args.granularity,
        "persisted_to": str(output) if output else "",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _query(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    common = {
        "root": root,
        "granularity": args.granularity,
        "max_files": args.max_files,
        "include_tests": not args.no_tests,
        "persist": args.persist,
    }
    if args.mode == "bm25":
        retriever = BM25Retriever.from_repository(**common)
    elif args.mode == "embedding":
        retriever = EmbeddingRetriever.from_repository(**common)
    else:
        retriever = HybridRetriever.from_repository(
            **common,
            enable_embeddings=args.embeddings,
        )

    results = retriever.retrieve(args.query, top_k=args.top_k)
    if args.json:
        payload = {
            "query": args.query,
            "count": len(results),
            "results": [
                {
                    "doc_id": result.document.doc_id,
                    "path": result.document.path,
                    "kind": result.document.kind,
                    "symbol": result.document.symbol,
                    "start_line": result.document.start_line,
                    "end_line": result.document.end_line,
                    "score": result.score,
                    "source": result.source,
                    "rank": result.rank,
                }
                for result in results
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_retrieved_context(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
