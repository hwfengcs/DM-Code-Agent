"""RAG功能测试脚本（简化版，避免milvus-lite依赖问题）"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dm_agent.rag import RAGManager
from dm_agent.rag.chunk import chunk_text


def test_chunk_text():
    """测试文本分块功能"""
    print("=" * 60)
    print("测试文本分块功能")
    print("=" * 60)

    test_text = """
    星辰电动ES9是一款未来旗舰电动SUV，拥有超长续航里程和智能座舱。
    以人为本的座舱设计，提供极致舒适体验和智能交互。
    高性能电池技术，支持超快充电，续航里程超过1000公里。
    """

    chunks = chunk_text(test_text, 50)

    print(f"\n✓ 成功将文本分割为 {len(chunks)} 个块")
    for i, chunk in enumerate(chunks, 1):
        print(f"\n  块 {i}: {chunk[:50]}...")

    print("\n" + "=" * 60)
    print("文本分块测试通过！")
    print("=" * 60)

    return True


def test_rag_manager_import():
    """测试RAG管理器导入"""
    print("\n" + "=" * 60)
    print("测试RAG管理器导入")
    print("=" * 60)

    try:
        from dm_agent.rag import RAGManager
        print("✓ RAGManager导入成功")

        rag_manager = RAGManager()
        print("✓ RAGManager实例创建成功")

        print(f"✓ 模型路径: {rag_manager._model_path}")
        print(f"✓ 数据库路径: {rag_manager._db_path}")
        print(f"✓ 数据目录: {rag_manager._data_dir}")

        print("\n" + "=" * 60)
        print("RAG管理器导入测试通过！")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rag_tools():
    """测试RAG工具导入"""
    print("\n" + "=" * 60)
    print("测试RAG工具导入")
    print("=" * 60)

    try:
        from dm_agent.tools.rag_tools import rag_search
        print("✓ rag_search函数导入成功")

        print("\n" + "=" * 60)
        print("RAG工具导入测试通过！")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tools_integration():
    """测试工具集成"""
    print("\n" + "=" * 60)
    print("测试工具集成")
    print("=" * 60)

    try:
        from dm_agent.tools import default_tools

        tools = default_tools(include_rag=True)
        print(f"✓ 成功获取工具列表，共 {len(tools)} 个工具")

        rag_tool = None
        for tool in tools:
            if tool.name == "rag_search":
                rag_tool = tool
                break

        if rag_tool:
            print(f"✓ 找到rag_search工具")
            print(f"✓ 工具描述: {rag_tool.description[:80]}...")
        else:
            print("✗ 未找到rag_search工具")
            return False

        print("\n" + "=" * 60)
        print("工具集成测试通过！")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_agent_integration():
    """测试Agent集成"""
    print("\n" + "=" * 60)
    print("测试Agent集成")
    print("=" * 60)

    try:
        from dm_agent.core.agent import ReactAgent
        from dm_agent.clients import create_llm_client

        print("✓ ReactAgent和create_llm_client导入成功")

        print("\n注意: 完整Agent测试需要API密钥，此处仅测试导入")
        print("✓ Agent集成导入测试通过")

        print("\n" + "=" * 60)
        print("Agent集成测试通过！")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    results = []

    results.append(("文本分块", test_chunk_text()))
    results.append(("RAG管理器导入", test_rag_manager_import()))
    results.append(("RAG工具导入", test_rag_tools()))
    results.append(("工具集成", test_tools_integration()))
    results.append(("Agent集成", test_agent_integration()))

    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name}: {status}")

    all_passed = all(result for _, result in results)

    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过！")
    else:
        print("部分测试失败，请检查错误信息")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)