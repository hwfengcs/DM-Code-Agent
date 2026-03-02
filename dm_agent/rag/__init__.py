"""RAG模块 - 提供文档检索和知识库管理功能"""

from .rag_manager import RAGManager
from .chunk import chunk_text

__all__ = ["RAGManager", "chunk_text"]