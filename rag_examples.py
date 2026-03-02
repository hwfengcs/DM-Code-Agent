"""RAG功能使用示例

展示如何使用重构后的RAG系统：
1. 直接使用RAGManager
2. 通过Agent使用RAG工具
3. 批量添加文档和检索
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dm_agent.rag import RAGManager
from dm_agent.tools import default_tools
from dm_agent.core.agent import ReactAgent
from dm_agent.clients import create_llm_client


def example_1_direct_usage():
    """示例1: 直接使用RAGManager"""
    print("=" * 70)
    print("示例1: 直接使用RAGManager")
    print("=" * 70)

    try:
        rag_manager = RAGManager()
        rag_manager.initialize()

        print("\n✓ RAG管理器初始化成功")
        print(f"✓ 模型路径: {rag_manager._model_path}")
        print(f"✓ 数据库路径: {rag_manager._db_path}")

        print("\n添加示例文档...")
        documents = [
            "星辰电动ES9是一款未来旗舰电动SUV，拥有超长续航里程和智能座舱。",
            "以人为本的座舱设计，提供极致舒适体验和智能交互。",
            "高性能电池技术，支持超快充电，续航里程超过1000公里。",
            "智能驾驶系统，支持L3级别自动驾驶，提供全方位安全保障。",
            "豪华内饰设计，采用环保材料，打造健康舒适的驾乘空间。"
        ]

        metadatas = [
            {"source": "doc1", "title": "ES9介绍"},
            {"source": "doc2", "title": "座舱设计"},
            {"source": "doc3", "title": "电池技术"},
            {"source": "doc4", "title": "智能驾驶"},
            {"source": "doc5", "title": "内饰设计"}
        ]

        count = rag_manager.add_documents(documents, metadatas)
        print(f"✓ 成功添加 {count} 个文档块")

        print("\n执行检索...")
        query = "什么是以人为本的座舱"
        results = rag_manager.search(query, top_k=3)

        print(f"✓ 检索到 {len(results)} 条结果:")
        for i, result in enumerate(results, 1):
            print(f"\n  结果 {i}:")
            print(f"    文本: {result['text']}")
            print(f"    分数: {result['score']:.4f}")
            print(f"    来源: {result['metadata'].get('source', 'N/A')}")
            print(f"    标题: {result['metadata'].get('title', 'N/A')}")

        stats = rag_manager.get_stats()
        print(f"\n✓ 数据库统计: {stats['total_documents']} 个文档块")

    except Exception as e:
        print(f"\n✗ 示例执行失败: {e}")
        import traceback
        traceback.print_exc()


def example_2_tools_integration():
    """示例2: 使用RAG工具"""
    print("\n" + "=" * 70)
    print("示例2: 使用RAG工具")
    print("=" * 70)

    try:
        from dm_agent.tools.rag_tools import rag_search

        print("\n✓ rag_search工具导入成功")

        print("\n执行检索...")
        result = rag_search({
            "query": "ES9的续航里程",
            "top_k": 2
        })

        print(f"✓ 检索结果:\n{result}")

    except Exception as e:
        print(f"\n✗ 示例执行失败: {e}")
        import traceback
        traceback.print_exc()


def example_3_agent_integration():
    """示例3: 通过Agent与RAG集成"""
    print("\n" + "=" * 70)
    print("示例3: 通过Agent与RAG集成")
    print("=" * 70)

    try:
        print("\n✓ 获取默认工具（包含RAG工具）")
        tools = default_tools(include_rag=True)

        rag_tool = None
        for tool in tools:
            if tool.name == "rag_search":
                rag_tool = tool
                break

        if rag_tool:
            print(f"✓ 找到rag_search工具")
            print(f"✓ 工具描述: {rag_tool.description[:100]}...")

        print("\n注意: 完整Agent示例需要API密钥")
        print("示例代码:")
        print("""
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
        """)

    except Exception as e:
        print(f"\n✗ 示例执行失败: {e}")
        import traceback
        traceback.print_exc()


def example_4_batch_documents():
    """示例4: 批量添加文档"""
    print("\n" + "=" * 70)
    print("示例4: 批量添加文档")
    print("=" * 70)

    try:
        rag_manager = RAGManager()
        rag_manager.initialize()

        print("\n✓ RAG管理器初始化成功")

        print("\n创建测试文档目录...")
        test_dir = "/tmp/test_rag_docs"
        os.makedirs(test_dir, exist_ok=True)

        test_files = {
            "product_info.txt": "星辰电动ES9产品信息\n\n未来旗舰电动SUV，超长续航，智能座舱。",
            "tech_specs.txt": "技术规格\n\n续航里程: 1000+公里\n充电时间: 30分钟\n电池容量: 150kWh"
        }

        for filename, content in test_files.items():
            filepath = os.path.join(test_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ 创建测试文件: {filename}")

        print("\n批量加载文档...")
        count = rag_manager.add_documents_from_directory(test_dir)
        print(f"✓ 成功加载 {count} 个文档块")

        print("\n执行检索...")
        query = "技术规格"
        results = rag_manager.search(query, top_k=2)

        print(f"✓ 检索到 {len(results)} 条结果:")
        for i, result in enumerate(results, 1):
            print(f"\n  结果 {i}:")
            print(f"    文本: {result['text'][:80]}...")
            print(f"    分数: {result['score']:.4f}")

    except Exception as e:
        print(f"\n✗ 示例执行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("RAG功能使用示例")
    print("=" * 70)

    example_1_direct_usage()
    example_2_tools_integration()
    example_3_agent_integration()
    example_4_batch_documents()

    print("\n" + "=" * 70)
    print("所有示例执行完成！")
    print("=" * 70)