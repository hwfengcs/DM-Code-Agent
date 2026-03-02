# RAG模块重构文档

## 概述

本次重构将原有的RAG demo代码封装为可复用的接口，集成到Agent工具系统中，提供文档检索和知识库管理功能。

## 重构内容

### 1. 核心组件

#### RAGManager (`dm_agent/rag/rag_manager.py`)
- **功能**: RAG系统核心管理器，采用单例模式
- **特性**:
  - BGE-M3模型懒加载（首次使用时初始化）
  - Milvus数据库连接和集合管理
  - 文档索引和删除功能
  - 混合向量检索（稀疏+密集向量）
- **主要方法**:
  - `initialize()`: 初始化RAG系统
  - `add_documents()`: 添加文档到知识库
  - `add_documents_from_directory()`: 批量加载目录文档
  - `search()`: 检索相关文档
  - `delete_all_documents()`: 清空数据库
  - `get_stats()`: 获取统计信息

#### RAG工具 (`dm_agent/tools/rag_tools.py`)
- **功能**: 为Agent提供RAG查询工具
- **工具名称**: `rag_search`
- **参数**:
  - `query` (str, required): 查询文本
  - `top_k` (int, optional): 返回结果数量，默认5
  - `hybrid_search_ratio` (float, optional): 混合搜索比例，默认0.5
- **返回格式**: JSON结构化数据，包含results、total、query

### 2. 文件结构

```
dm_agent/
├── rag/
│   ├── __init__.py              # 导出RAGManager和chunk_text
│   ├── rag_manager.py            # RAG管理器核心类
│   ├── chunk.py                  # 文本分块功能
│   └── rag_demo.py              # 原demo代码（已重命名）
├── tools/
│   ├── rag_tools.py              # RAG查询工具
│   └── __init__.py              # 集成rag_search工具
├── data/
│   ├── milvus.db                # Milvus数据库（自动创建）
│   └── documents/                # 文档存储目录
└── model/
    └── bge-m3/                  # BGE-M3模型（已存在）
```

### 3. Agent集成

#### 初始化参数
```python
agent = ReactAgent(
    client,
    tools,
    enable_rag=True,              # 是否启用RAG
    rag_config={                  # RAG配置（可选）
        "model_path": "/path/to/model",
        "db_path": "/path/to/milvus.db",
        "data_dir": "/path/to/documents",
        "llama_parse_api_key": "your-api-key"
    }
)
```

#### 工具集成
- RAG工具自动添加到Agent工具列表
- Agent可以自主决定何时使用rag_search工具

## 使用示例

### 示例1: 直接使用RAGManager

```python
from dm_agent.rag import RAGManager

# 创建RAG管理器
rag_manager = RAGManager()
rag_manager.initialize()

# 添加文档
documents = ["文档1内容", "文档2内容"]
metadatas = [{"source": "doc1"}, {"source": "doc2"}]
rag_manager.add_documents(documents, metadatas)

# 检索文档
results = rag_manager.search("查询文本", top_k=5)
for result in results:
    print(f"文本: {result['text']}")
    print(f"分数: {result['score']}")
    print(f"元数据: {result['metadata']}")
```

### 示例2: 使用RAG工具

```python
from dm_agent.tools.rag_tools import rag_search

# 执行检索
result = rag_search({
    "query": "查询文本",
    "top_k": 3,
    "hybrid_search_ratio": 0.5
})

# 解析结果
import json
data = json.loads(result)
for item in data["results"]:
    print(item["text"])
```

### 示例3: 通过Agent使用RAG

```python
from dm_agent import ReactAgent, create_llm_client, default_tools

# 创建LLM客户端
client = create_llm_client(
    provider="deepseek",
    api_key="your-api-key"
)

# 创建Agent（自动启用RAG）
agent = ReactAgent(
    client,
    default_tools(include_rag=True),
    enable_rag=True
)

# 执行任务（Agent会自动使用rag_search工具）
result = agent.run("查询ES9的座舱设计特点")
print(result["final_answer"])
```

### 示例4: 批量加载文档

```python
from dm_agent.rag import RAGManager

rag_manager = RAGManager()
rag_manager.initialize()

# 从目录批量加载
count = rag_manager.add_documents_from_directory(
    "/path/to/documents",
    chunk_size=300,
    file_extensions=['.pdf', '.txt', '.md']
)

print(f"成功加载 {count} 个文档块")
```

## 配置说明

### 默认路径
- **模型路径**: `/home/tianwenkai/workspace/DM-Code-Agent/dm_agent/model`
- **数据库路径**: `/home/tianwenkai/workspace/DM-Code-Agent/dm_agent/data/milvus.db`
- **文档目录**: `/home/tianwenkai/workspace/DM-Code-Agent/dm_agent/data/documents`

### 自定义配置
```python
rag_manager = RAGManager(
    model_path="/custom/path/to/model",
    db_path="/custom/path/to/milvus.db",
    data_dir="/custom/path/to/documents",
    llama_parse_api_key="your-api-key"
)
```

## 依赖安装

```bash
pip install pymilvus[milvus_lite]>=2.3.0
pip install milvus-model>=0.3.0
pip install huggingface-hub>=0.20.0
pip install llama-index>=0.10.0
pip install llama-cloud-services>=0.1.0
```

或使用requirements.txt:
```bash
pip install -r requirements.txt
```

## 技术特性

### 1. 单例模式
- RAGManager使用单例模式确保全局唯一实例
- 避免重复加载模型和数据库连接

### 2. 懒加载
- 模型仅在首次使用时加载
- 数据库在首次检索时连接

### 3. 混合向量检索
- 使用BGE-M3的稀疏和密集向量
- 支持混合搜索比例调整

### 4. 文档分块
- 智能文本分块，保持段落完整性
- 支持表格和特殊格式处理

### 5. 错误处理
- 完善的异常处理机制
- RAG工具失败不会导致Agent崩溃

## 测试

### 运行测试脚本
```bash
# 简化测试（无需milvus-lite）
python test_rag_simple.py

# 完整测试（需要milvus-lite）
python test_rag.py
```

### 运行示例
```bash
python rag_examples.py
```

## 注意事项

1. **模型下载**: 首次运行会自动下载BGE-M3模型（约2.3GB）
2. **PDF解析**: 需要LlamaParse API密钥
3. **数据库持久化**: Milvus数据库自动保存到本地
4. **线程安全**: RAGManager使用线程锁确保并发安全
5. **内存管理**: 大量文档建议分批添加

## 故障排除

### 问题1: milvus-lite依赖错误
```bash
pip install pymilvus[milvus_lite]
pip install setuptools
```

### 问题2: 模型下载失败
- 检查网络连接
- 手动下载模型到指定目录

### 问题3: 数据库连接失败
- 检查数据库路径权限
- 确保milvus-lite正确安装

## 后续优化

1. 支持更多文档格式（Word、Excel等）
2. 添加文档更新和删除功能
3. 实现增量索引
4. 添加检索结果缓存
5. 支持分布式部署

## 参考文档

- [BGE-M3模型](https://github.com/FlagOpen/FlagEmbedding)
- [Milvus向量数据库](https://milvus.io/)
- [LlamaIndex](https://docs.llamaindex.ai/)

## 版本历史

- **v1.0.0** (2025-03-02)
  - 初始版本
  - 完成RAG系统重构
  - 集成到Agent工具系统