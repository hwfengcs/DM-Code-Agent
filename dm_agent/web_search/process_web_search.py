
try:
    # 尝试相对导入（作为模块运行时）
    from . import serper_search, process_search_results
except ImportError:
    # 回退到直接导入（直接运行文件时）
    from dm_agent.web_search import serper_search, process_search_results
import chromadb
from typing import List
from openai import OpenAI
import os
def generate_embedding(text: str, api_key: str = "", base_url: str = "", model_name: str = "text-embedding-v3", dimensions: int = 1024, encoding_format: "Literal['float', 'base64']" = "float"):
    api_key = os.getenv("DASHSCOPE_API_KEY") or ""
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"    

    # 初始化 OpenAI 客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )

    # 调用 OpenAI 的嵌入接口
    try:
        completion = client.embeddings.create(
            model=model_name,
            input=text,
            dimensions=dimensions,
            encoding_format=encoding_format  # type: ignore
        )
        embedding = completion.data[0].embedding
        return embedding
    except Exception as e:
        print(f"OpenAI API 请求失败: {e}")
        return [0.0] * 1024  # 返回零向量而不是 None


# 初始化 ChromaDB 客户端（内存模式）
chroma_client = chromadb.Client()

def embed_text(text: str | List[str]) -> List[List[float]]:
    """生成文本嵌入向量"""
    if isinstance(text, str):
        text = [text]
    
    embeddings = []
    for t in text:
        embedding = generate_embedding(t)
        if embedding is not None:
            # 确保返回的是列表格式
            if isinstance(embedding, list):
                embeddings.append(embedding)
            else:
                # 如果是其他格式（如numpy数组），转换为列表
                embeddings.append(embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding))
        else:
            # 如果生成失败，返回一个全零向量
            embeddings.append([0.0] * 1024)  # 假设维度为 1024
    return embeddings

# 初始化 ChromaDB 客户端（内存模式）
chroma_client = chromadb.Client()

def store_and_query_snippets(question: str, top_k: int = 5):
    """
    将 snippets 存储到 ChromaDB，并与 question 计算相似度，返回前 top_k 条最相关的结果。

    参数:
        snippets (List[Dict]): 包含 title, url, content 的 snippets 列表
        question (str): 查询问题
        top_k (int): 返回的最相关结果数量，默认为 5

    返回:
        List[Dict]: 最相关的前 top_k 条结果，包含 title, url, content
    """
    # 使用自定义嵌入函数

    search_results = serper_search(question)
    snippets, related_questions = process_search_results(search_results)

    # 创建一个临时集合（collection），使用自定义嵌入函数
    # 先检查集合是否已存在，如果存在则删除
    try:
        existing_collection = chroma_client.get_collection(name="temp_snippets")
        chroma_client.delete_collection(name="temp_snippets")
    except:
        # 集合不存在，继续创建
        pass
    
    collection = chroma_client.create_collection(name="temp_snippets")

    # 将 snippets 存储到 ChromaDB
    documents = []
    metadatas = []
    ids = []
    
    for idx, snippet in enumerate(snippets):
        documents.append(snippet["content"])
        metadatas.append({"title": snippet["title"], "url": snippet["url"]})
        ids.append(str(idx))
    
    # 添加文档
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    # 使用问题文本查询最相关的结果
    results = collection.query(
        query_texts=[question],  # 查询问题
        n_results=top_k  # 返回前 top_k 条结果
    )

    # 解析查询结果
    top_snippets = []
    if results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            snippet_id = results["ids"][0][i]
            content = results["documents"][0][i] if results["documents"] and results["documents"][0] else ""
            metadata = results["metadatas"][0][i] if results["metadatas"] and results["metadatas"][0] else {}
            top_snippets.append({
                "title": metadata.get("title", ""),
                "url": metadata.get("url", ""),
                "content": content
            })

    # 删除临时集合，释放内存
    chroma_client.delete_collection(name="temp_snippets")

    return top_snippets, related_questions

if __name__=='__main__':
    # 假设 search_results 是 search 函数的返回值
    snippets, questions = store_and_query_snippets(question="apex英雄")
    
    # 打印 snippet 列表
    print("Snippets:")
    for snippet in snippets:
        print(snippet)
    
    # 打印 question 列表
    print("\nQuestions:")
    for question in questions:
        print(question)