"""前端开发专家技能"""

from __future__ import annotations

from typing import List

from ..base import BaseSkill, SkillMetadata
from ...tools.base import Tool


class FrontendDevSkill(BaseSkill):
    """前端开发专家技能"""

    def get_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="frontend_dev",
            display_name="前端开发专家",
            description="提供 HTML/CSS/JavaScript/React/Vue/TypeScript 开发最佳实践和性能优化指导",
            keywords=[
                "html",
                "css",
                "javascript",
                "react",
                "vue",
                "typescript",
                "前端",
                "npm",
                "yarn",
                "webpack",
                "vite",
                "tailwind",
                "nextjs",
                "nuxt",
                "组件",
                "状态管理",
                "响应式",
            ],
            patterns=[
                r"\.(html|css|jsx|tsx|vue)\b",
                r"\bnpm\s+",
                r"\byarn\s+",
                r"\bcomponent\b",
                r"\buseState\b",
            ],
            priority=5,
            version="1.0.0",
        )

    def get_prompt_addition(self) -> str:
        return (
            "你现在具备前端开发专家能力。在处理前端相关任务时请遵循以下原则：\n"
            "1. 编写语义化 HTML，遵循无障碍访问标准\n"
            "2. 使用现代 CSS 技术（Flexbox、Grid、CSS Variables）\n"
            "3. React/Vue 组件设计遵循单一职责原则\n"
            "4. 合理管理状态，避免 prop drilling\n"
            "5. 关注 Web 性能：代码分割、懒加载、图片优化\n"
            "6. TypeScript 优先，充分利用类型系统\n"
            "7. 编写可复用、可测试的组件\n"
        )

    def get_tools(self) -> List[Tool]:
        # 前端技能不提供额外工具，现有 run_shell 已可执行 npm/yarn 命令
        return []
