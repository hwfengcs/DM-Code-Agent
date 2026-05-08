import json

import pytest

from dm_agent.memory.retriever import (
    BM25Retriever,
    EmbeddingRetriever,
    HybridRetriever,
    RetrievalDocument,
    build_repository_documents,
    default_cache_path,
    format_retrieved_context,
    load_or_build_documents,
    save_documents,
    tokenize,
)
from dm_agent.memory.index_cli import main as index_main


def _docs():
    return [
        RetrievalDocument(
            doc_id="function:auth.py:1:validate_token",
            path="auth.py",
            kind="function",
            symbol="validate_token",
            start_line=1,
            end_line=2,
            content="def validate_token(token):\n    return token == 'ok'\n",
        ),
        RetrievalDocument(
            doc_id="function:cache.py:1:load_user",
            path="cache.py",
            kind="function",
            symbol="load_user",
            start_line=1,
            end_line=2,
            content="def load_user(user_id):\n    return cache[user_id]\n",
        ),
        RetrievalDocument(
            doc_id="function:billing.py:1:charge_invoice",
            path="billing.py",
            kind="function",
            symbol="charge_invoice",
            start_line=1,
            end_line=2,
            content="def charge_invoice(invoice):\n    return gateway.charge(invoice)\n",
        ),
    ]


def test_tokenize_splits_snake_and_camel_case():
    tokens = tokenize("validateToken retry_error")

    assert "validate" in tokens
    assert "token" in tokens
    assert "retry" in tokens
    assert "error" in tokens


def test_build_repository_documents_indexes_symbols(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "auth.py").write_text(
        "class TokenStore:\n"
        "    def validate_token(self, token: str) -> bool:\n"
        "        return token == 'ok'\n\n"
        "def refresh_token(user_id: str) -> str:\n"
        "    return user_id + '-fresh'\n",
        encoding="utf-8",
    )

    documents = build_repository_documents(tmp_path)

    assert {document.kind for document in documents} == {"class", "method", "function"}
    assert any(document.symbol == "TokenStore.validate_token" for document in documents)
    assert any(document.symbol == "refresh_token" for document in documents)


def test_bm25_retriever_ranks_keyword_match_first():
    retriever = BM25Retriever(_docs())

    results = retriever.retrieve("token validation failed", top_k=2)

    assert results[0].document.path == "auth.py"
    assert results[0].source == "bm25"
    assert results[0].score > 0


def test_embedding_retriever_supports_injected_encoder():
    vectors = {
        "def validate_token(token):\n    return token == 'ok'\n": [1.0, 0.0],
        "auth failure": [1.0, 0.0],
    }

    def encoder(texts):
        encoded = []
        for text in texts:
            if "validate_token" in text:
                encoded.append([1.0, 0.0])
            elif "auth" in text:
                encoded.append(vectors["auth failure"])
            elif "load_user" in text:
                encoded.append([0.0, 1.0])
            else:
                encoded.append([0.2, 0.2])
        return encoded

    retriever = EmbeddingRetriever(_docs(), encoder=encoder)

    results = retriever.retrieve("auth failure", top_k=1)

    assert results[0].document.path == "auth.py"
    assert results[0].source == "embedding"


def test_embedding_retriever_requires_optional_dependency_without_encoder(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="sentence-transformers"):
        EmbeddingRetriever(_docs())


def test_hybrid_retriever_uses_rrf_fusion():
    def encoder(texts):
        encoded = []
        for text in texts:
            if "charge_invoice" in text or "payment issue" in text:
                encoded.append([1.0, 0.0])
            elif "validate_token" in text:
                encoded.append([0.8, 0.1])
            else:
                encoded.append([0.0, 1.0])
        return encoded

    bm25 = BM25Retriever(_docs())
    embedding = EmbeddingRetriever(_docs(), encoder=encoder)
    retriever = HybridRetriever(bm25=bm25, embedding=embedding)

    results = retriever.retrieve("payment issue token", top_k=3)

    assert len(results) >= 2
    assert {result.document.path for result in results[:2]} == {"auth.py", "billing.py"}
    assert all(result.source.startswith("hybrid:") for result in results)


def test_persisted_documents_reuse_cache_until_mtime_changes(tmp_path):
    module = tmp_path / "app.py"
    module.write_text("def alpha():\n    return 'alpha'\n", encoding="utf-8")

    first = load_or_build_documents(tmp_path, persist=True)
    cache_path = default_cache_path(tmp_path)
    assert cache_path.exists()

    second = load_or_build_documents(tmp_path, persist=True)
    assert [document.doc_id for document in second] == [document.doc_id for document in first]

    module.write_text(
        "def alpha():\n    return 'alpha'\n\n" "def beta():\n    return 'beta'\n",
        encoding="utf-8",
    )
    third = load_or_build_documents(tmp_path, persist=True)

    assert any(document.symbol == "beta" for document in third)


def test_save_documents_round_trip(tmp_path):
    path = tmp_path / "index.json"
    save_documents(_docs(), path, root=tmp_path)

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["documents"][0]["path"] == "auth.py"


def test_format_retrieved_context_is_bounded():
    results = BM25Retriever(_docs()).retrieve("token", top_k=1)

    context = format_retrieved_context(results, max_chars=120)

    assert context.startswith("<retrieved_context>")
    assert "auth.py" in context
    assert context.endswith("</retrieved_context>")


def test_index_cli_build_and_query(tmp_path, capsys):
    (tmp_path / "auth.py").write_text(
        "def validate_token(token):\n    return token == 'ok'\n",
        encoding="utf-8",
    )

    assert index_main(["build", "--root", str(tmp_path), "--persist"]) == 0
    build_output = json.loads(capsys.readouterr().out)
    assert build_output["document_count"] == 1
    assert build_output["persisted_to"]

    assert (
        index_main(
            [
                "query",
                "token validation",
                "--root",
                str(tmp_path),
                "--top-k",
                "1",
                "--json",
                "--persist",
            ]
        )
        == 0
    )
    query_output = json.loads(capsys.readouterr().out)
    assert query_output["results"][0]["path"] == "auth.py"
