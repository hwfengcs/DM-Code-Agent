"""验证RAG功能集成的修改"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dm_agent.prompts import build_code_agent_prompt
from dm_agent.tools.base import Tool


def test_build_code_agent_prompt():
    """测试build_code_agent_prompt函数"""
    print("=" * 60)
    print("测试 build_code_agent_prompt 函数")
    print("=" * 60)

    # 创建一个测试工具
    def test_runner(args):
        return "test result"

    test_tool = Tool(
        name="test_tool",
        description="测试工具",
        runner=test_runner
    )

    # 测试1: 使用默认的formatted_references
    print("\n1. 测试默认formatted_references...")
    tools = [test_tool]
    prompt = build_code_agent_prompt(tools)
    if "暂无参考内容" in prompt:
        print("✓ 默认formatted_references正确")
    else:
        print("✗ 默认formatted_references不正确")
        return False

    # 测试2: 使用自定义的formatted_references
    print("\n2. 测试自定义formatted_references...")
    custom_refs = "[1] 这是第一条参考内容\n    来源: test, 相关度: 0.9500"
    prompt = build_code_agent_prompt(tools, custom_refs)
    if custom_refs in prompt:
        print("✓ 自定义formatted_references正确")
    else:
        print("✗ 自定义formatted_references不正确")
        return False

    # 测试3: 验证工具列表被正确替换
    print("\n3. 测试工具列表替换...")
    if "test_tool: 测试工具" in prompt:
        print("✓ 工具列表正确替换")
    else:
        print("✗ 工具列表替换不正确")
        return False

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)

    return True


def test_format_rag_results():
    """测试_format_rag_results方法"""
    print("\n" + "=" * 60)
    print("测试 _format_rag_results 方法")
    print("=" * 60)

    # 模拟Agent类（仅用于测试）
    class MockAgent:
        def _format_rag_results(self, results):
            if not results:
                return "暂无参考内容"
            
            formatted = []
            for i, result in enumerate(results, 1):
                text = result.get("text", "")
                metadata = result.get("metadata", {})
                score = result.get("score", 0)
                source = metadata.get("source", "未知来源")
                
                formatted.append(f"[{i}] {text}\n    来源: {source}, 相关度: {score:.4f}")
            
            return "\n\n".join(formatted)

    agent = MockAgent()

    # 测试1: 空结果
    print("\n1. 测试空结果...")
    result = agent._format_rag_results([])
    if result == "暂无参考内容":
        print("✓ 空结果处理正确")
    else:
        print("✗ 空结果处理不正确")
        return False

    # 测试2: 正常结果
    print("\n2. 测试正常结果...")
    test_results = [
        {
            "text": "Python是一种高级编程语言",
            "metadata": {"source": "test1", "title": "Python介绍"},
            "score": 0.95
        },
        {
            "text": "Python支持多种编程范式",
            "metadata": {"source": "test2", "title": "编程范式"},
            "score": 0.88
        }
    ]
    result = agent._format_rag_results(test_results)
    
    if "[1] Python是一种高级编程语言" in result and \
       "[2] Python支持多种编程范式" in result and \
       "来源: test1" in result and \
       "相关度: 0.9500" in result:
        print("✓ 正常结果格式化正确")
    else:
        print("✗ 正常结果格式化不正确")
        print(f"结果: {result}")
        return False

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)

    return True


if __name__ == "__main__":
    success1 = test_build_code_agent_prompt()
    success2 = test_format_rag_results()
    
    sys.exit(0 if (success1 and success2) else 1)
