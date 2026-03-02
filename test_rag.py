"""RAG功能测试脚本"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dm_agent.rag import RAGManager


def test_rag_manager():
    """测试RAG管理器基本功能"""
    print("=" * 60)
    print("开始测试RAG管理器")
    print("=" * 60)

    try:
        print("\n1. 初始化RAG管理器...")
        rag_manager = RAGManager()
        rag_manager.initialize()
        print("✓ RAG管理器初始化成功")

        print("\n2. 获取统计信息...")
        stats = rag_manager.get_stats()
        print(f"✓ 统计信息: {stats}")

        print("\n3. 添加测试文档...")
        test_docs = [
            "星辰电动ES9是一款未来旗舰电动SUV，拥有超长续航里程和智能座舱。",
            "以人为本的座舱设计，提供极致舒适体验和智能交互。",
            "高性能电池技术，支持超快充电，续航里程超过1000公里。"
        ]
        metadatas = [
            {"source": "test1", "title": "ES9介绍"},
            {"source": "test2", "title": "座舱设计"},
            {"source": "test3", "title": "电池技术"}
        ]
        count = rag_manager.add_documents(test_docs, metadatas)
        print(f"✓ 成功添加 {count} 个文档块")

        print("\n4. 执行检索测试...")
        query = "什么是以人为本的座舱"
        results = rag_manager.search(query, top_k=3)
        print(f"✓ 检索到 {len(results)} 条结果")
        for i, result in enumerate(results, 1):
            print(f"\n  结果 {i}:")
            print(f"    文本: {result['text'][:50]}...")
            print(f"    分数: {result['score']:.4f}")
            print(f"    元数据: {result['metadata']}")

        print("\n5. 更新统计信息...")
        stats = rag_manager.get_stats()
        print(f"✓ 当前文档总数: {stats['total_documents']}")

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
    success = test_rag_manager()
    sys.exit(0 if success else 1)