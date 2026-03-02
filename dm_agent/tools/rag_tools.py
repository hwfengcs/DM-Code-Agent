"""RAG工具 - 为Agent提供文档检索功能"""

import json
from typing import Any, Dict

from ..rag.rag_manager import RAGManager


def rag_search(arguments: Dict[str, Any]) -> str:
    """使用RAG系统检索相关文档

    该工具通过混合向量检索（稀疏+密集向量）在知识库中查找与查询相关的文档片段。
    支持自定义返回结果数量和混合搜索比例。

    Args:
        arguments (Dict[str, Any]): 工具调用参数字典
            - query (str, required): 查询文本，用于检索相关文档
            - top_k (int, optional): 返回结果数量，默认为5
            - hybrid_search_ratio (float, optional): 混合搜索比例（0-1），默认0.5
              0表示完全使用稀疏向量，1表示完全使用密集向量

    Returns:
        str: JSON格式的检索结果，包含：
            - results (list): 检索结果列表，每个结果包含：
                - text (str): 文档内容
                - score (float): 相关性分数
                - metadata (dict): 文档元数据（如source, chunk_id等）
            - total (int): 返回结果总数
            - query (str): 原始查询文本

    Raises:
        ValueError: 当缺少必需参数或参数类型错误时
        RuntimeError: 当RAG系统未初始化或检索失败时

    Examples:
        >>> rag_search({"query": "什么是以人为本的座舱"})
        '{"results": [{"text": "...", "score": 0.95, "metadata": {...}}], "total": 5, "query": "什么是以人为本的座舱"}'

        >>> rag_search({"query": "ES9的续航里程", "top_k": 3})
        '{"results": [...], "total": 3, "query": "ES9的续航里程"}'
    """
    if not isinstance(arguments, dict):
        raise ValueError("参数必须是一个字典")

    if "query" not in arguments:
        raise ValueError("缺少必需参数: query")

    query = arguments["query"]
    if not isinstance(query, str) or not query.strip():
        raise ValueError("参数query必须是非空字符串")

    top_k = arguments.get("top_k", 5)
    if not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("参数top_k必须是正整数")

    hybrid_search_ratio = arguments.get("hybrid_search_ratio", 0.5)
    if not isinstance(hybrid_search_ratio, (int, float)) or not (0 <= hybrid_search_ratio <= 1):
        raise ValueError("参数hybrid_search_ratio必须是0-1之间的数字")

    try:
        rag_manager = RAGManager()
        if not rag_manager.is_initialized():
            rag_manager.initialize()

        results = rag_manager.search(
            query=query.strip(),
            top_k=top_k,
            hybrid_search_ratio=hybrid_search_ratio
        )

        response = {
            "results": results,
            "total": len(results),
            "query": query.strip()
        }

        return json.dumps(response, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = f"RAG检索失败: {str(e)}"
        return json.dumps({
            "error": error_msg,
            "results": [],
            "total": 0,
            "query": query.strip()
        }, ensure_ascii=False, indent=2)