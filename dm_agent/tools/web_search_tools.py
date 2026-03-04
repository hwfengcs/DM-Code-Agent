from typing import Any, Dict


def web_search_answer(arguments: Dict[str, Any]) -> str:
    query = arguments.get("query", "")
    if not isinstance(query, str):
        raise ValueError("参数 'query' 必须是字符串")
    
    query = query.strip()
    if not query:
        raise ValueError("参数 'query' 不能为空")
    
    try:
        try:
            # 尝试相对导入（作为模块运行时）
            from ..web_search.process_web_search import store_and_query_snippets
        except ImportError:
            # 回退到绝对导入（直接运行文件时）
            import sys
            from pathlib import Path
            sys.path.append(str(Path(__file__).parent.parent.parent))
            from dm_agent.web_search.process_web_search import store_and_query_snippets
        
        # search_results = serper_search(query)
        # snippets, related_questions = process_search_results(search_results)
        snippets, related_questions = store_and_query_snippets(query)


        if not snippets:
            return f"未找到关于 '{query}' 的搜索结果。"
        
        result_lines = [f"搜索 '{query}' 的结果：\n"]
        for idx, snippet in enumerate(snippets, 1):
            result_lines.append(f"{idx}. {snippet['title']}")
            result_lines.append(f"   URL: {snippet['url']}")
            result_lines.append(f"   {snippet['content']}\n")
        
        if related_questions:
            result_lines.append("相关问题：")
            for question in related_questions[:5]:
                result_lines.append(f"  - {question}")
        
        return "\n".join(result_lines)
        
    except Exception as e:
        error_msg = f"网络搜索失败: {str(e)}"
        print(error_msg)
        return error_msg

if __name__=='__main__':
    # 假设 search_results 是 search 函数的返回值
    snippets = web_search_answer({"query": "apex英雄"})
    


    print(snippets)
