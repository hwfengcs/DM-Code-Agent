"""Python 专家技能"""

from __future__ import annotations

from typing import Any, Dict, List

from ..base import BaseSkill, SkillMetadata
from ...tools.base import Tool

_PYTHON_BEST_PRACTICES: Dict[str, str] = {
    "代码风格": (
        "- 遵循 PEP 8 代码风格指南\n"
        "- 使用 4 个空格缩进\n"
        "- 行宽不超过 88 字符（black 默认）\n"
        "- 使用有意义的变量和函数命名"
    ),
    "类型提示": (
        "- 使用 type hints 标注函数签名\n"
        "- 对复杂类型使用 typing 模块\n"
        "- 使用 from __future__ import annotations 延迟解析\n"
        "- 运行 mypy 做静态类型检查"
    ),
    "异常处理": (
        "- 捕获具体异常而非裸 except\n"
        "- 使用 try/except/else/finally 完整结构\n"
        "- 自定义异常继承 Exception 或其子类\n"
        "- 记录异常上下文信息"
    ),
    "性能优化": (
        "- 使用生成器处理大数据集\n"
        "- 利用列表推导式代替 map/filter\n"
        "- 使用 collections 模块（Counter, defaultdict 等）\n"
        "- 使用 functools.lru_cache 缓存计算结果\n"
        "- 避免在循环内做不必要的计算"
    ),
    "项目结构": (
        "- 使用 pyproject.toml 管理项目配置\n"
        "- 按功能模块划分包结构\n"
        "- 将常量、配置、工具函数分离\n"
        "- 编写 __init__.py 控制公开 API"
    ),
    "测试": (
        "- 使用 pytest 作为测试框架\n"
        "- 编写单元测试和集成测试\n"
        "- 使用 fixtures 管理测试数据\n"
        "- 目标覆盖率 >= 80%"
    ),
    "异步编程": (
        "- 使用 async/await 语法\n"
        "- 使用 asyncio.gather 并行执行多个协程\n"
        "- 使用 aiohttp / httpx 做异步 HTTP 请求\n"
        "- 注意异步上下文管理器"
    ),
}


def _python_best_practices_runner(arguments: Dict[str, Any]) -> str:
    """按主题查询 Python 最佳实践建议"""
    topic = arguments.get("topic", "").strip()
    if not topic:
        topics_list = "、".join(_PYTHON_BEST_PRACTICES.keys())
        return f"请提供要查询的主题。可选主题：{topics_list}"

    topic_lower = topic.lower()
    # 精确匹配
    if topic in _PYTHON_BEST_PRACTICES:
        return f"## Python 最佳实践 — {topic}\n\n{_PYTHON_BEST_PRACTICES[topic]}"

    # 模糊匹配
    for key, value in _PYTHON_BEST_PRACTICES.items():
        if topic_lower in key.lower() or key.lower() in topic_lower:
            return f"## Python 最佳实践 — {key}\n\n{value}"

    # 返回全部
    all_practices = "\n\n".join(
        f"### {key}\n{value}" for key, value in _PYTHON_BEST_PRACTICES.items()
    )
    return f"未找到主题 '{topic}' 的精确匹配，以下是所有最佳实践：\n\n{all_practices}"


class PythonExpertSkill(BaseSkill):
    """Python 专家技能"""

    def get_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="python_expert",
            display_name="Python 专家",
            description="提供 Python 编程最佳实践、代码规范和性能优化指导",
            keywords=[
                "python",
                "pip",
                "pytest",
                "async",
                "类型提示",
                "dataclass",
                "装饰器",
                "生成器",
                "虚拟环境",
                "venv",
                "poetry",
                "pyproject",
                "pydantic",
                "fastapi",
                "flask",
                "django",
            ],
            patterns=[
                r"\.py\b",
                r"\bimport\s+\w+",
                r"\bdef\s+\w+",
                r"\bclass\s+\w+",
                r"\basync\s+def\b",
            ],
            priority=5,
            version="1.0.0",
        )

    def get_prompt_addition(self) -> str:
        return (
            "你现在具备 Python 专家能力。在处理 Python 相关任务时请遵循以下原则：\n"
            "1. 始终遵循 PEP 8 代码风格，使用类型提示\n"
            "2. 优先使用 Python 标准库和成熟的第三方库\n"
            "3. 编写可测试、可维护的代码，适当使用 dataclass 和 typing\n"
            "4. 注意性能优化：使用生成器、列表推导式、缓存等技术\n"
            "5. 正确处理异常，使用 logging 记录关键信息\n"
            "6. 使用 python_best_practices 工具查询特定领域的最佳实践建议\n"
        )

    def get_tools(self) -> List[Tool]:
        return [
            Tool(
                name="python_best_practices",
                description=(
                    "查询 Python 最佳实践建议。"
                    '参数：{"topic": "主题名称"}，'
                    "可选主题：代码风格、类型提示、异常处理、性能优化、项目结构、测试、异步编程"
                ),
                runner=_python_best_practices_runner,
            )
        ]
