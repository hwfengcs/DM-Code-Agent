"""Repository context retrieval for opt-in RAG prompts."""

from __future__ import annotations

import ast
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence

from ..tools.code_index_tools import DEFAULT_INDEX_EXCLUDES

CACHE_DIR = ".dm-agent-cache"
INDEX_DIR = "index"
DOCUMENTS_FILENAME = "documents.json"
DEFAULT_MAX_FILES = 200
DEFAULT_TOP_K = 5
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[\u4e00-\u9fff]+")


@dataclass(frozen=True)
class RetrievalDocument:
    """A chunk of repository context that can be retrieved."""

    doc_id: str
    path: str
    content: str
    kind: str = "file"
    start_line: int = 1
    end_line: int = 1
    symbol: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    """A scored retrieval hit."""

    document: RetrievalDocument
    score: float
    source: str
    rank: int = 0


class TextEncoder(Protocol):
    """Small protocol shared by sentence-transformers and test doubles."""

    def encode(self, texts: Sequence[str], **kwargs: Any) -> Any:
        """Encode a list of texts into vectors."""


def build_repository_documents(
    root: str | Path,
    *,
    granularity: str = "symbol",
    max_files: int = DEFAULT_MAX_FILES,
    include_tests: bool = True,
) -> List[RetrievalDocument]:
    """Build retrieval documents from Python files under ``root``.

    ``granularity`` can be:
    - ``symbol``: top-level functions/classes and class methods, with file fallback.
    - ``file``: one document per Python file.
    - ``both``: file documents plus symbol documents.
    """

    if granularity not in {"symbol", "file", "both"}:
        raise ValueError("granularity must be one of: symbol, file, both")

    root_path = Path(root).resolve()
    if not root_path.exists():
        raise ValueError(f"Repository root does not exist: {root_path}")
    if not root_path.is_dir():
        raise ValueError(f"Repository root is not a directory: {root_path}")

    documents: List[RetrievalDocument] = []
    for path in _iter_python_files(root_path, max_files=max_files, include_tests=include_tests):
        relative = path.relative_to(root_path).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines = source.splitlines()
        mtime = path.stat().st_mtime
        file_metadata = {"mtime": mtime, "size": path.stat().st_size}

        if granularity in {"file", "both"}:
            documents.append(
                RetrievalDocument(
                    doc_id=f"file:{relative}",
                    path=relative,
                    content=source,
                    kind="file",
                    start_line=1,
                    end_line=max(len(lines), 1),
                    metadata=file_metadata,
                )
            )

        if granularity in {"symbol", "both"}:
            symbol_documents = _symbol_documents(relative, source, lines, file_metadata)
            documents.extend(symbol_documents)
            if not symbol_documents and granularity == "symbol":
                documents.append(
                    RetrievalDocument(
                        doc_id=f"file:{relative}",
                        path=relative,
                        content=source,
                        kind="file",
                        start_line=1,
                        end_line=max(len(lines), 1),
                        metadata=file_metadata,
                    )
                )

    return documents


def load_or_build_documents(
    root: str | Path,
    *,
    granularity: str = "symbol",
    max_files: int = DEFAULT_MAX_FILES,
    include_tests: bool = True,
    persist: bool = False,
    cache_dir: str | Path | None = None,
) -> List[RetrievalDocument]:
    """Load a persisted index when mtimes still match; otherwise rebuild it."""

    root_path = Path(root).resolve()
    cache_path = _cache_path(root_path, cache_dir)
    if persist and cache_path.exists():
        try:
            cached_payload = _load_payload(cache_path)
            if cached_payload.get("granularity") != granularity:
                raise ValueError("Cached retrieval index granularity does not match.")
            cached_documents = _documents_from_payload(cached_payload)
            cached_manifest = _manifest_from_documents(cached_documents)
            current_manifest = _current_manifest(
                root_path, max_files=max_files, include_tests=include_tests
            )
            if cached_manifest == current_manifest:
                return cached_documents
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    documents = build_repository_documents(
        root_path,
        granularity=granularity,
        max_files=max_files,
        include_tests=include_tests,
    )
    if persist:
        save_documents(documents, cache_path, root=root_path, granularity=granularity)
    return documents


def save_documents(
    documents: Sequence[RetrievalDocument],
    path: str | Path,
    *,
    root: str | Path | None = None,
    granularity: str = "symbol",
) -> None:
    """Persist retrieval documents as JSON."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "root": str(Path(root).resolve()) if root is not None else "",
        "granularity": granularity,
        "documents": [asdict(document) for document in documents],
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_documents(path: str | Path) -> List[RetrievalDocument]:
    """Load retrieval documents from JSON."""

    payload = _load_payload(path)
    return _documents_from_payload(payload)


def _load_payload(path: str | Path) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported retrieval index schema.")
    return payload


def _documents_from_payload(payload: Dict[str, Any]) -> List[RetrievalDocument]:
    documents = []
    for item in payload.get("documents", []):
        documents.append(
            RetrievalDocument(
                doc_id=str(item["doc_id"]),
                path=str(item["path"]),
                content=str(item["content"]),
                kind=str(item.get("kind", "file")),
                start_line=int(item.get("start_line", 1)),
                end_line=int(item.get("end_line", 1)),
                symbol=str(item.get("symbol", "")),
                metadata=dict(item.get("metadata", {})),
            )
        )
    return documents


class _SimpleBM25:
    """Tiny BM25 implementation used when rank-bm25 is not installed."""

    def __init__(self, tokenized_corpus: Sequence[Sequence[str]], *, k1: float, b: float) -> None:
        self.corpus = [list(tokens) for tokens in tokenized_corpus]
        self.k1 = k1
        self.b = b
        self.doc_count = len(self.corpus)
        self.doc_lengths = [len(tokens) for tokens in self.corpus]
        self.avg_doc_length = sum(self.doc_lengths) / self.doc_count if self.doc_count > 0 else 0.0
        self.term_frequencies = [Counter(tokens) for tokens in self.corpus]
        document_frequencies: Counter[str] = Counter()
        for tokens in self.corpus:
            document_frequencies.update(set(tokens))
        self.idf = {
            term: math.log(1 + (self.doc_count - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequencies.items()
        }

    def get_scores(self, query_tokens: Sequence[str]) -> List[float]:
        scores = []
        for index, frequencies in enumerate(self.term_frequencies):
            score = 0.0
            doc_length = self.doc_lengths[index] or 1
            for token in query_tokens:
                frequency = frequencies.get(token, 0)
                if frequency <= 0:
                    continue
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * doc_length / (self.avg_doc_length or 1)
                )
                score += self.idf.get(token, 0.0) * frequency * (self.k1 + 1) / denominator
            scores.append(score)
        return scores


class BM25Retriever:
    """Keyword retriever backed by rank-bm25 when available."""

    def __init__(
        self,
        documents: Sequence[RetrievalDocument],
        *,
        tokenizer: Callable[[str], List[str]] | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.documents = list(documents)
        self.tokenizer = tokenizer or tokenize
        self._tokenized_corpus = [
            self.tokenizer(_document_text(document)) for document in documents
        ]
        self._backend = self._build_backend(self._tokenized_corpus, k1=k1, b=b)

    @classmethod
    def from_repository(
        cls,
        root: str | Path,
        *,
        granularity: str = "symbol",
        max_files: int = DEFAULT_MAX_FILES,
        include_tests: bool = True,
        persist: bool = False,
        cache_dir: str | Path | None = None,
    ) -> "BM25Retriever":
        documents = load_or_build_documents(
            root,
            granularity=granularity,
            max_files=max_files,
            include_tests=include_tests,
            persist=persist,
            cache_dir=cache_dir,
        )
        return cls(documents)

    def retrieve(self, query: str, *, top_k: int = DEFAULT_TOP_K) -> List[RetrievalResult]:
        query_tokens = self.tokenizer(query)
        if not query_tokens or not self.documents:
            return []

        scores = list(self._backend.get_scores(query_tokens))
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        results = []
        for rank, (index, score) in enumerate(ranked[:top_k], start=1):
            if score <= 0:
                continue
            results.append(
                RetrievalResult(
                    document=self.documents[index],
                    score=float(score),
                    source="bm25",
                    rank=rank,
                )
            )
        return results

    @staticmethod
    def _build_backend(
        tokenized_corpus: Sequence[Sequence[str]],
        *,
        k1: float,
        b: float,
    ) -> Any:
        try:
            from rank_bm25 import BM25Okapi

            return BM25Okapi(tokenized_corpus, k1=k1, b=b)
        except ImportError:
            return _SimpleBM25(tokenized_corpus, k1=k1, b=b)


class EmbeddingRetriever:
    """Semantic retriever using optional sentence-transformers or an injected encoder."""

    def __init__(
        self,
        documents: Sequence[RetrievalDocument],
        *,
        encoder: TextEncoder | Callable[[Sequence[str]], Any] | None = None,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.documents = list(documents)
        self.encoder = encoder or self._load_sentence_transformer(model_name)
        self._embeddings = self._encode([_document_text(document) for document in self.documents])

    @classmethod
    def from_repository(
        cls,
        root: str | Path,
        *,
        granularity: str = "symbol",
        max_files: int = DEFAULT_MAX_FILES,
        include_tests: bool = True,
        persist: bool = False,
        cache_dir: str | Path | None = None,
        encoder: TextEncoder | Callable[[Sequence[str]], Any] | None = None,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
    ) -> "EmbeddingRetriever":
        documents = load_or_build_documents(
            root,
            granularity=granularity,
            max_files=max_files,
            include_tests=include_tests,
            persist=persist,
            cache_dir=cache_dir,
        )
        return cls(documents, encoder=encoder, model_name=model_name)

    def retrieve(self, query: str, *, top_k: int = DEFAULT_TOP_K) -> List[RetrievalResult]:
        if not query.strip() or not self.documents:
            return []

        query_vector = self._encode([query])[0]
        scored = [
            (index, _cosine_similarity(query_vector, document_vector))
            for index, document_vector in enumerate(self._embeddings)
        ]
        ranked = sorted(scored, key=lambda item: item[1], reverse=True)
        results = []
        for rank, (index, score) in enumerate(ranked[:top_k], start=1):
            if score <= 0:
                continue
            results.append(
                RetrievalResult(
                    document=self.documents[index],
                    score=float(score),
                    source="embedding",
                    rank=rank,
                )
            )
        return results

    def _encode(self, texts: Sequence[str]) -> List[List[float]]:
        if callable(self.encoder) and not hasattr(self.encoder, "encode"):
            raw_vectors = self.encoder(texts)
        else:
            raw_vectors = self.encoder.encode(texts, normalize_embeddings=True)  # type: ignore[union-attr]
        return [_as_float_list(vector) for vector in raw_vectors]

    @staticmethod
    def _load_sentence_transformer(model_name: str) -> TextEncoder:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "EmbeddingRetriever requires sentence-transformers. "
                'Install it with: pip install "dm-code-agent[rag]", or inject an encoder.'
            ) from exc
        return SentenceTransformer(model_name)


class HybridRetriever:
    """Fuse keyword and embedding retrieval with Reciprocal Rank Fusion."""

    def __init__(
        self,
        bm25: BM25Retriever | None = None,
        embedding: EmbeddingRetriever | None = None,
        *,
        rrf_k: int = 60,
        bm25_weight: float = 1.0,
        embedding_weight: float = 1.0,
    ) -> None:
        if bm25 is None and embedding is None:
            raise ValueError("HybridRetriever requires at least one retrieval backend.")
        self.bm25 = bm25
        self.embedding = embedding
        self.rrf_k = rrf_k
        self.bm25_weight = bm25_weight
        self.embedding_weight = embedding_weight

    @classmethod
    def from_repository(
        cls,
        root: str | Path,
        *,
        granularity: str = "symbol",
        max_files: int = DEFAULT_MAX_FILES,
        include_tests: bool = True,
        persist: bool = False,
        cache_dir: str | Path | None = None,
        enable_embeddings: bool = False,
        encoder: TextEncoder | Callable[[Sequence[str]], Any] | None = None,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
    ) -> "HybridRetriever":
        documents = load_or_build_documents(
            root,
            granularity=granularity,
            max_files=max_files,
            include_tests=include_tests,
            persist=persist,
            cache_dir=cache_dir,
        )
        bm25 = BM25Retriever(documents)
        embedding = (
            EmbeddingRetriever(documents, encoder=encoder, model_name=model_name)
            if enable_embeddings or encoder is not None
            else None
        )
        return cls(bm25=bm25, embedding=embedding)

    def retrieve(self, query: str, *, top_k: int = DEFAULT_TOP_K) -> List[RetrievalResult]:
        pools: List[tuple[float, List[RetrievalResult]]] = []
        backend_top_k = max(top_k * 2, top_k)
        if self.bm25:
            pools.append((self.bm25_weight, self.bm25.retrieve(query, top_k=backend_top_k)))
        if self.embedding:
            pools.append(
                (self.embedding_weight, self.embedding.retrieve(query, top_k=backend_top_k))
            )

        documents_by_id: Dict[str, RetrievalDocument] = {}
        sources_by_id: Dict[str, set[str]] = defaultdict(set)
        fused_scores: Dict[str, float] = defaultdict(float)
        raw_scores: Dict[str, float] = defaultdict(float)

        for weight, results in pools:
            for rank, result in enumerate(results, start=1):
                doc_id = result.document.doc_id
                documents_by_id[doc_id] = result.document
                sources_by_id[doc_id].add(result.source)
                fused_scores[doc_id] += weight / (self.rrf_k + rank)
                raw_scores[doc_id] = max(raw_scores[doc_id], result.score)

        ranked_doc_ids = sorted(
            fused_scores,
            key=lambda doc_id: (fused_scores[doc_id], raw_scores[doc_id]),
            reverse=True,
        )
        return [
            RetrievalResult(
                document=documents_by_id[doc_id],
                score=float(fused_scores[doc_id]),
                source="hybrid:" + "+".join(sorted(sources_by_id[doc_id])),
                rank=rank,
            )
            for rank, doc_id in enumerate(ranked_doc_ids[:top_k], start=1)
        ]


def format_retrieved_context(
    results: Sequence[RetrievalResult],
    *,
    max_chars: int = 6000,
) -> str:
    """Render retrieval hits as a bounded prompt block."""

    if not results:
        return ""

    lines = ["<retrieved_context>"]
    used_chars = 0
    for result in results:
        document = result.document
        header = (
            f"[{result.rank}] {document.path}:{document.start_line}-{document.end_line} "
            f"({document.kind}"
        )
        if document.symbol:
            header += f" {document.symbol}"
        header += f", score={result.score:.4f}, source={result.source})"
        snippet = _truncate(document.content.strip(), max_chars=max_chars - used_chars)
        if not snippet:
            break
        lines.extend([header, "```python", snippet, "```"])
        used_chars += len(header) + len(snippet)
        if used_chars >= max_chars:
            break
    lines.append("</retrieved_context>")
    return "\n".join(lines)


def tokenize(text: str) -> List[str]:
    """Tokenize natural language and code-ish text for BM25."""

    tokens: List[str] = []
    for match in _TOKEN_PATTERN.findall(text):
        parts = re.split(r"_+", match)
        for part in parts:
            tokens.extend(_split_camel_case(part))
    return [token for token in tokens if token]


def default_cache_path(root: str | Path) -> Path:
    """Return the default persisted index path for a repository root."""

    return _cache_path(Path(root).resolve(), None)


def _iter_python_files(root: Path, *, max_files: int, include_tests: bool) -> Iterable[Path]:
    count = 0
    excludes = set(DEFAULT_INDEX_EXCLUDES) | {CACHE_DIR}
    for path in sorted(root.rglob("*.py")):
        relative_parts = path.relative_to(root).parts
        if any(part in excludes for part in relative_parts):
            continue
        if not include_tests and any(part in {"test", "tests"} for part in relative_parts):
            continue
        yield path
        count += 1
        if count >= max_files:
            break


def _symbol_documents(
    relative: str,
    source: str,
    lines: Sequence[str],
    file_metadata: Dict[str, Any],
) -> List[RetrievalDocument]:
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError:
        return []

    documents: List[RetrievalDocument] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            documents.append(_document_from_node(relative, lines, node, "class", file_metadata))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    documents.append(
                        _document_from_node(
                            relative,
                            lines,
                            item,
                            "method",
                            file_metadata,
                            parent=node.name,
                        )
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            documents.append(_document_from_node(relative, lines, node, "function", file_metadata))
    return documents


def _document_from_node(
    relative: str,
    lines: Sequence[str],
    node: ast.AST,
    kind: str,
    file_metadata: Dict[str, Any],
    *,
    parent: str = "",
) -> RetrievalDocument:
    name = getattr(node, "name", kind)
    symbol = f"{parent}.{name}" if parent else str(name)
    start_line = int(getattr(node, "lineno", 1))
    end_line = int(getattr(node, "end_lineno", start_line))
    content = "\n".join(lines[start_line - 1 : end_line])
    metadata = dict(file_metadata)
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        metadata["docstring"] = ast.get_docstring(node)
    return RetrievalDocument(
        doc_id=f"{kind}:{relative}:{start_line}:{symbol}",
        path=relative,
        content=content,
        kind=kind,
        start_line=start_line,
        end_line=end_line,
        symbol=symbol,
        metadata=metadata,
    )


def _document_text(document: RetrievalDocument) -> str:
    fields = [
        document.path,
        document.kind,
        document.symbol,
        str(document.metadata.get("docstring", "")),
        document.content,
    ]
    return "\n".join(field for field in fields if field)


def _manifest_from_documents(documents: Sequence[RetrievalDocument]) -> Dict[str, Dict[str, Any]]:
    manifest: Dict[str, Dict[str, Any]] = {}
    for document in documents:
        metadata = document.metadata
        manifest[document.path] = {
            "mtime": metadata.get("mtime"),
            "size": metadata.get("size"),
        }
    return manifest


def _current_manifest(
    root: Path, *, max_files: int, include_tests: bool
) -> Dict[str, Dict[str, Any]]:
    manifest = {}
    for path in _iter_python_files(root, max_files=max_files, include_tests=include_tests):
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        manifest[relative] = {"mtime": stat.st_mtime, "size": stat.st_size}
    return manifest


def _cache_path(root: Path, cache_dir: str | Path | None) -> Path:
    base = Path(cache_dir) if cache_dir is not None else root / CACHE_DIR / INDEX_DIR
    return base / DOCUMENTS_FILENAME


def _split_camel_case(token: str) -> List[str]:
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", token).split()
    if len(parts) == 1:
        return parts
    return [part.lower() for part in parts] + [token.lower()]


def _as_float_list(vector: Any) -> List[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(value) for value in vector]


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _truncate(text: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max(max_chars - 16, 0)].rstrip() + "\n# ... truncated ..."
