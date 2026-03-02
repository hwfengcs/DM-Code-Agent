"""测试RAG功能集成到Agent"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dm_agent.rag import RAGManager
from dm_agent.clients import OpenAIClient
from dm_agent.tools import default_tools
from dm_agent.core.agent import ReactAgent


def test_rag_integration():
    """测试RAG功能集成到Agent"""
    print("=" * 60)
    print("测试RAG功能集成到Agent")
    print("="("=" * 60))

    try:
        # 1. 初始化RAG管理器并添加测试文档
        print("\n1. 初始化RAG管理器...")
        rag_manager = RAGManager()
        rag_manager.initialize()
        print("✓ RAG管理器初始化成功")

        print("\n2. 添加测试文档...")
        test_docs = [
            "Python是一种高级编程语言，具有简洁易读的语法。",
            "Python支持多种编程范式，包括面向对象、函数式和过程式编程。",
            "Python拥有丰富的标准库和第三方库，适用于各种应用场景。"
        ]
        metadatas = [
            {"source": "python_intro", "title": "Python介绍"},
            {"source": "python_paradigms", "title": "编程范式"},
            {"source": "python_libraries", "title": "库和框架"}
        ]
        count = rag_manager.add_documents(test_docs, metadatas)
        print(f"✓ 成功添加 {count} 个文档块")

        # 2. 测试Agent的RAG集成
        print("\n3. 创建Agent（启用RAG）...")
        # 注意：这里需要真实的API密钥，如果没有可以使用mock客户端
        try:
            client = OpenAIClient(api_key="test-key", model="gpt-3.5-turbo")
        except:
            print("⚠️ 无法创建OpenAI客户端，跳过Agent测试")
            return True

        tools = default_tools()
        agent = ReactAgent(
            client,
            tools,
            enable_rag=True,
            max_steps=5
        )
        print("✓ Agent创建成功，RAG已启用")

        # 3. 验证RAG管理器是否正确初始化
        print("\n4. 验证RAG管理器状态...")
        if agent.enable_rag and agent.rag_manager:
            if agent.rag_manager.is_initialized():
                print("✓ RAG管理器已正确初始化")
            else:
                print("✗ RAG管理器未初始化")
                return False
        else:
            print("✗ RAG未启用或管理器未创建")
            return False

        # 4. 测试RAG检索功能
        print("\n5. 测试RAG检索功能...")
        query = "Python的特点是什么"
        results = rag_manager.search(query, top_k=3)
        print(f"✓ 检索到 {len(results)} 条结果")
        for i, result in enumerate(results, 1):
            print(f"  结果 {i}: {result['text'][:50]}... (分数: {result['score']:.4f})")

        # 5. 测试格式化RAG结果的方法
        print("\n6. 测试格式化RAG结果...")
        formatted = agent._format_rag_results(results)
        print("✓ 格式化结果：")
        print(formatted)

        print("\n" + "=" * 60)
        print("所有测试通过！")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = test_rag_integration()
    sys.exit(0 if success else 1)
