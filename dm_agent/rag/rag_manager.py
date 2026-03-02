"""RAG管理器 - 提供文档索引和检索功能"""

import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
import threading

try:
    from huggingface_hub import snapshot_download
    from milvus_model.hybrid import BGEM3EmbeddingFunction
    from pymilvus import (
        connections,
        utility,
        FieldSchema,
        CollectionSchema,
        DataType,
        Collection,
        WeightedRanker,
        AnnSearchRequest,
    )
    from llama_index.core import SimpleDirectoryReader
    from llama_cloud_services import LlamaParse
except ImportError as e:
    raise ImportError(
        f"RAG功能需要安装额外依赖: {e}\n"
        "请运行: pip install pymilvus milvus-model huggingface-hub llama-index llama"
    )

from .chunk import chunk_text


class RAGManager:
    """RAG管理器 - 单例模式，负责文档管理、索引和检索"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        model_path: Optional[str] = None,
        db_path: Optional[str] = None,
        data_dir: Optional[str] = None,
        llama_parse_api_key: Optional[str] = None,
    ):
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self._model_path = model_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "model"
        )
        self._db_path = db_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "milvus.db"
        )
        self._data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "documents"
        )
        self._llama_parse_api_key = llama_parse_api_key

        self._embedding_function = None
        self._collection = None
        self._collection_name = "hybrid_rag"
        self._is_initialized = False

    def initialize(self) -> None:
        """初始化RAG系统（模型和数据库）"""
        if self._is_initialized:
            return

        try:
            self._init_model()
            self._init_database()
            self._is_initialized = True
        except Exception as e:
            raise RuntimeError(f"RAG系统初始化失败: {e}")

    def _init_model(self) -> None:
        """初始化BGE-M3嵌入模型"""
        if not os.path.exists(self._model_path):
            print(f"正在下载BGE-M3模型到 {self._model_path}...")
            os.makedirs(self._model_path, exist_ok=True)
            snapshot_download(
                "BAAI/bge-m3",
                local_dir=self._model_path,
                local_dir_use_symlinks=False
            )
            print("模型下载完成")

        self._embedding_function = BGEM3EmbeddingFunction(
            model_name_or_path=self._model_path,
            use_fp16=False,
            device="cpu"
        )

    def _init_database(self) -> None:
        """初始化Milvus数据库"""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        connections.connect(uri=self._db_path)

        if utility.has_collection(self._collection_name):
            self._collection = Collection(self._collection_name)
        else:
            self._create_collection()

        self._collection.load()

    def _create_collection(self) -> None:
        """创建Milvus集合"""
        dense_dim = self._embedding_function.dim["dense"]

        fields = [
            FieldSchema(
                name="pk",
                dtype=DataType.VARCHAR,
                is_primary=True,
                auto_id=True,
                max_length=100
            ),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
            FieldSchema(name="dense_vector", dtype=DataType.FLOAT_VECTOR, dim=dense_dim),
        ]

        schema = CollectionSchema(fields, description="RAG文档集合")
        self._collection = Collection(self._collection_name, schema)

        sparse_index = {"index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP"}
        self._collection.create_index("sparse_vector", sparse_index)

        dense_index = {"index_type": "AUTOINDEX", "metric_type": "IP"}
        self._collection.create_index("dense_vector", dense_index)

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        chunk_size: int = 300
    ) -> int:
        """添加文档到知识库

        Args:
            documents: 文档文本列表
            metadatas: 文档元数据列表（可选）
            chunk_size: 文本分块大小

        Returns:
            添加的文档块数量
        """
        if not self._is_initialized:
            self.initialize()

        if not documents:
            return 0

        if metadatas is None:
            metadatas = [{} for _ in documents]

        all_chunks = []
        all_metadatas = []

        for doc_text, metadata in zip(documents, metadatas):
            chunks = chunk_text(doc_text, chunk_size)
            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                chunk_metadata = metadata.copy()
                chunk_metadata["chunk_id"] = i
                chunk_metadata["chunk_total"] = len(chunks)
                all_metadatas.append(chunk_metadata)

        if not all_chunks:
            return 0

        embeddings = self._embedding_function(all_chunks)

        entities = [
            all_chunks,
            [json.dumps(m, ensure_ascii=False) for m in all_metadatas],
            embeddings["sparse"],
            embeddings["dense"],
        ]

        self._collection.insert(entities)
        self._collection.flush()

        return len(all_chunks)

    def add_documents_from_directory(
        self,
        directory: str,
        chunk_size: int = 300,
        file_extensions: Optional[List[str]] = None
    ) -> int:
        """从目录批量加载文档

        Args:
            directory: 文档目录路径
            chunk_size: 文本分块大小
            file_extensions: 支持的文件扩展名（如['.pdf', '.txt', '.md']）

        Returns:
            添加的文档块数量
        """
        if not os.path.exists(directory):
            raise ValueError(f"目录不存在: {directory}")

        if file_extensions is None:
            file_extensions = ['.pdf', '.txt', '.md', '.rst']

        documents = []
        metadatas = []

        for ext in file_extensions:
            pattern = f"**/*{ext}"
            for file_path in Path(directory).rglob(pattern):
                try:
                    if ext == '.pdf':
                        text = self._parse_pdf(file_path)
                    else:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            text = f.read()

                    if text.strip():
                        documents.append(text)
                        metadatas.append({
                            "source": str(file_path),
                            "filename": file_path.name,
                            "file_type": ext
                        })
                except Exception as e:
                    print(f"警告: 无法读取文件 {file_path}: {e}")

        return self.add_documents(documents, metadatas, chunk_size)

    def _parse_pdf(self, file_path: str) -> str:
        """解析PDF文件"""
        if not self._llama_parse_api_key:
            raise ValueError("需要LlamaParse API密钥来解析PDF文件")

        parse = LlamaParse(
            api_key=self._llama_parse_api_key,
            result_type="markdown",
            num_workers=3,
            verbose=False,
            language="ch_sim",
        )

        documents = SimpleDirectoryReader(
            input_files=[str(file_path)],
            file_extractor={'.pdf': parse}
        ).load_data()

        return '\n'.join([doc.text for doc in documents])

    def search(
        self,
        query: str,
        top_k: int = 5,
        hybrid_search_ratio: float = 0.5
    ) -> List[Dict[str, Any]]:
        """检索相关文档

        Args:
            query: 查询文本
            top_k: 返回结果数量
            hybrid_search_ratio: 混合搜索比例（0-1，偏向稀疏或密集向量）

        Returns:
            检索结果列表，每个结果包含text, score, metadata
        """
        if not self._is_initialized:
            self.initialize()

        if not query.strip():
            return []

        query_embedding = self._embedding_function([query])

        search_params = {
            "metric_type": "IP",
            "params": {}
        }

        dense_req = AnnSearchRequest(
            [query_embedding["dense"][0]], "dense_vector", search_params, limit=top_k
        )
        sparse_req = AnnSearchRequest(
            [query_embedding["sparse"][0]], "sparse_vector", search_params, limit=top_k
        )

        rerank = WeightedRanker(1.0, 1.0)

        results = self._collection.hybrid_search(
            [sparse_req, dense_req], rerank=rerank, limit=top_k, output_fields=["text", "metadata"]
        )

        formatted_results = []
        for hit in results[0]:
            metadata = json.loads(hit.get("metadata") or "{}")
            formatted_results.append({
                "text": hit.get("text") or "",
                "score": hit.score,
                "metadata": metadata
            })

        return formatted_results

    def delete_all_documents(self) -> None:
        """清空所有文档"""
        if not self._is_initialized:
            return

        self._collection.delete(expr="pk != ''")
        self._collection.flush()

    def get_stats(self) -> Dict[str, Any]:
        """获取RAG系统统计信息"""
        if not self._is_initialized:
            return {
                "initialized": False,
                "total_documents": 0
            }

        stats = {
            "initialized": True,
            "collection_name": self._collection_name,
            "total_documents": self._collection.num_entities,
            "model_path": self._model_path,
            "db_path": self._db_path,
            "data_dir": self._data_dir
        }

        return stats

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._is_initialized