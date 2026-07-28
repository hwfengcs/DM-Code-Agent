# Skill 系统接入指南

本文档介绍 DM-Code-Agent 的可插拔 Skill（专家能力）系统。Skill 系统允许 Agent 根据任务自动激活相关的领域专家能力，每个 Skill 包含专用的 system prompt 补充和专用工具。

---

## 快速开始

### 1. 默认即可用

Skill 系统内置了 3 个专家技能，无需任何配置即可使用。启动系统后自动加载：

```bash
python main.py
```

你将会看到类似输出：

```
正在加载 MCP 服务器...
ℹ 未启用 MCP 服务器
✓ 加载了 3 个技能
```

### 2. 自动激活机制

Agent 会根据任务描述自动选择并激活最相关的技能（最多同时激活 3 个）：

```bash
python main.py "优化我 Django 项目中的 SQL 查询"
```

你会看到：

```
🎯 已激活技能：Python 专家, 数据库专家
📋 生成的执行计划：
...
```

### 3. 查看可用技能

在交互模式下选择菜单选项 `5. 查看可用技能列表`：

```
可用技能列表：

1. Python 专家
   标识：python_expert
   描述：提供 Python 编程最佳实践、代码规范和性能优化指导
   类型：内置  版本：1.0.0  专用工具：1 个
   关键词：python, pip, pytest, async, 类型提示, dataclass, 装饰器, 生成器...

2. 数据库专家
   标识：db_expert
   描述：提供 SQL 最佳实践、数据库设计、ORM 使用和性能优化指导
   类型：内置  版本：1.0.0  专用工具：1 个
   关键词：sql, mysql, postgresql, sqlite, 数据库, 索引, orm, sqlalchemy...

3. 前端开发专家
   标识：frontend_dev
   描述：提供 HTML/CSS/JavaScript/React/Vue/TypeScript 开发最佳实践和性能优化指导
   类型：内置  版本：1.0.0  专用工具：0 个
   关键词：html, css, javascript, react, vue, typescript, 前端, npm...
```

---

## 内置技能详解

### 1. Python 专家 (`python_expert`)

**自动激活条件**：任务中包含 `python`、`pip`、`pytest`、`async`、`类型提示`、`dataclass` 等关键词，或匹配 `.py`、`import`、`def`、`class` 等代码模式。

**增强能力**：
- 注入 Python 代码规范、最佳实践和性能优化指导到 system prompt
- 提供专用工具 `python_best_practices`

**专用工具 — `python_best_practices`**

按主题查询 Python 最佳实践建议。可选主题：

| 主题 | 内容 |
|------|------|
| 代码风格 | PEP 8、缩进、命名规范 |
| 类型提示 | type hints、typing 模块、mypy |
| 异常处理 | 具体异常捕获、上下文管理 |
| 性能优化 | 生成器、列表推导式、缓存 |
| 项目结构 | pyproject.toml、包结构 |
| 测试 | pytest、fixtures、覆盖率 |
| 异步编程 | async/await、asyncio |

**示例任务**：
```bash
python main.py "写一个解析 CSV 的 Python 脚本，要求使用类型提示"
python main.py "重构这个 Python 项目的异常处理逻辑"
python main.py "为 calculator.py 编写完整的 pytest 测试"
```

### 2. 数据库专家 (`db_expert`)

**自动激活条件**：任务中包含 `sql`、`mysql`、`postgresql`、`数据库`、`索引`、`orm` 等关键词，或匹配 `SELECT`、`CREATE TABLE`、`.sql` 等 SQL 模式。

**增强能力**：
- 注入 SQL 最佳实践、数据库设计和性能优化指导到 system prompt
- 提供专用工具 `sql_review`

**专用工具 — `sql_review`**

审查 SQL 语句，检测常见问题并给出优化建议。检测项目：

| 检测项 | 说明 |
|--------|------|
| SELECT * | 建议显式列出需要的列 |
| 无 WHERE 子句 | 可能导致全表扫描 |
| JOIN/WHERE 索引 | 建议创建合适的索引 |
| LIKE 前缀通配符 | 无法使用索引，建议全文索引 |

**示例任务**：
```bash
python main.py "优化这个 SQL 查询的性能"
python main.py "设计一个用户订单系统的数据库表结构"
python main.py "把这段 SQL 查询改写为 SQLAlchemy ORM"
```

### 3. 前端开发专家 (`frontend_dev`)

**自动激活条件**：任务中包含 `html`、`css`、`react`、`vue`、`typescript`、`前端`、`npm` 等关键词，或匹配 `.html`、`.css`、`.jsx`、`.tsx`、`.vue` 等文件模式。

**增强能力**：
- 注入 HTML/CSS 语义化、React/Vue 组件设计、Web 性能优化指导到 system prompt
- 无专用工具（现有 `run_shell` 已可执行 npm/yarn 命令）

**示例任务**：
```bash
python main.py "创建一个 React 组件来显示用户列表"
python main.py "用 Tailwind CSS 实现一个响应式导航栏"
python main.py "将这个 JavaScript 项目迁移到 TypeScript"
```

---

## 如何创建自定义技能

### 方法 1：通过 JSON 配置文件（推荐，简单场景）

这是最简单的方法，只需创建一个 JSON 文件即可。

#### 步骤 1：创建 JSON 文件

在 `dm_agent/skills/custom/` 目录下创建 `.json` 文件：

```json
{
  "name": "devops_expert",
  "display_name": "DevOps 专家",
  "description": "提供 Docker、Kubernetes、CI/CD 和云部署最佳实践指导",
  "keywords": ["docker", "kubernetes", "k8s", "ci/cd", "jenkins", "github actions", "部署", "容器", "devops"],
  "patterns": ["Dockerfile", "\\.ya?ml$", "docker-compose"],
  "priority": 10,
  "version": "1.0.0",
  "prompt_addition": "你现在具备 DevOps 专家能力。在处理 DevOps 相关任务时请遵循以下原则：\n1. 容器化优先，使用多阶段构建优化镜像大小\n2. 遵循 12-Factor App 原则\n3. CI/CD 流水线自动化测试和部署\n4. 使用 Infrastructure as Code 管理基础设施\n5. 注意安全扫描和密钥管理"
}
```

#### 步骤 2：重启系统

```bash
python main.py
```

系统会自动加载 `custom/` 目录下的所有 JSON 技能文件。

### 方法 2：通过 Python 类（复杂场景，需要自定义工具）

适用于需要提供专用工具的复杂技能。

#### 步骤 1：创建 Python 扩展与技能类

在用户扩展目录创建 `~/.dm_agent/extensions/security_expert.py`。这种方式不需要 fork 或修改
`dm_agent/` 内核源码：

```python
"""安全专家技能"""

from typing import Any, Dict, List
from dm_agent.skills import BaseSkill, SkillMetadata
from dm_agent.tools import Tool


def _security_check_runner(arguments: Dict[str, Any]) -> str:
    """安全检查工具"""
    code = arguments.get("code", "")
    # 实现安全检查逻辑
    findings = []
    if "eval(" in code:
        findings.append("⚠ 检测到 eval() 使用，存在代码注入风险")
    if "password" in code.lower() and "=" in code:
        findings.append("⚠ 检测到硬编码密码")
    if not findings:
        return "✅ 未检测到明显的安全问题"
    return "## 安全检查结果\n\n" + "\n".join(f"- {f}" for f in findings)


class SecurityExpertSkill(BaseSkill):
    def get_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="security_expert",
            display_name="安全专家",
            description="提供代码安全审计、漏洞检测和安全最佳实践指导",
            keywords=["安全", "漏洞", "xss", "sql注入", "加密", "认证", "授权"],
            patterns=[r"\bpassword\b", r"\bsecret\b", r"\btoken\b"],
            priority=8,
            version="1.0.0",
        )

    def get_prompt_addition(self) -> str:
        return (
            "你现在具备安全专家能力。请注意检查代码中的安全隐患，"
            "包括但不限于 SQL 注入、XSS、CSRF、硬编码密钥等问题。"
        )

    def get_tools(self) -> List[Tool]:
        return [
            Tool(
                name="security_check",
                description="检查代码中的安全隐患。参数：{\"code\": \"要检查的代码\"}",
                runner=_security_check_runner,
            )
        ]
```

#### 步骤 2：通过 ExtensionAPI 注册技能

在同一文件末尾导出 `setup(api)`：

```python
def setup(api) -> None:
    api.register_skill(SecurityExpertSkill())
```

#### 步骤 3：重启系统

```bash
python main.py
```

用户目录扩展由用户自行放置，默认加载。项目内 `.dm_agent/extensions/` 则必须先显式信任；
完整安全边界与 entry point 分发方式见 [扩展开发](extensions.md)。

---

## 技能选择机制

### 自动选择策略

Skill 系统采用混合选择策略，自动为任务匹配最相关的技能：

1. **关键词匹配**（默认）：遍历所有技能的 `keywords`，计算与任务文本的匹配度分数
2. **正则模式匹配**：检查 `patterns` 列表，匹配成功给更高权重（1.5 倍）
3. **LLM 辅助选择**（可选，默认关闭）：关键词无结果时，用一次 LLM 调用判断最相关技能

### 选择参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_active_skills` | 3 | 最多同时激活的技能数 |
| `min_keyword_score` | 0.05 | 最低匹配阈值（分数低于此值的技能不被选中） |
| `enable_llm_fallback` | False | 是否启用 LLM 辅助选择 |

### 自动激活示例

| 任务描述 | 激活的技能 |
|----------|------------|
| "优化我 Django 项目中的 SQL 查询" | python_expert + db_expert |
| "写一个解析 CSV 的 Python 脚本" | python_expert |
| "创建一个 React 组件来显示用户列表" | frontend_dev |
| "列出当前目录的文件" | （无技能激活，正常执行） |

---

## JSON 配置详解

### 配置文件结构

```json
{
  "name": "<技能唯一标识符>",
  "display_name": "<显示名称>",
  "description": "<技能描述>",
  "keywords": ["<关键词1>", "<关键词2>", ...],
  "patterns": ["<正则表达式1>", "<正则表达式2>", ...],
  "priority": 10,
  "version": "1.0.0",
  "prompt_addition": "<追加到 system prompt 的文本>"
}
```

### 字段说明

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `name` | ✅ | 技能唯一标识符 | `"devops_expert"` |
| `display_name` | ❌ | 显示名称，默认同 name | `"DevOps 专家"` |
| `description` | ❌ | 技能描述 | `"提供 DevOps 最佳实践指导"` |
| `keywords` | ❌ | 匹配关键词列表 | `["docker", "k8s", "部署"]` |
| `patterns` | ❌ | 正则匹配模式列表 | `["Dockerfile", "\\.ya?ml$"]` |
| `priority` | ❌ | 优先级，数值越小越高（默认 10） | `5` |
| `version` | ❌ | 版本号（默认 `"1.0.0"`） | `"1.0.0"` |
| `prompt_addition` | ❌ | 追加到 system prompt 的文本 | `"你具备 DevOps 专家能力..."` |

> **注意**：JSON 配置方式不支持自定义工具。如需提供专用工具，请使用 Python 类方式。

---

## 常见问题

### Q1: 技能没有被自动激活怎么办？

**可能原因**：
1. 任务描述中缺少匹配关键词
2. 匹配分数低于阈值

**解决方法**：
- 在任务描述中明确提及相关技术（如 "python"、"sql"、"react"）
- 查看技能的关键词列表，确认任务描述是否包含相关关键词

### Q2: 如何禁用技能自动激活？

创建 `ReactAgent` 时不传入 `skill_manager` 参数即可。技能系统完全可选，不影响 Agent 正常运行。

### Q3: 自定义技能 JSON 文件放在哪里？

放在 `dm_agent/skills/custom/` 目录下，文件扩展名为 `.json`。系统启动时会自动扫描该目录。

### Q4: 能否同时使用 Skill 系统和 MCP 工具？

可以！Skill 系统和 MCP 是完全独立的扩展机制，可以同时使用。Skill 提供领域专家 prompt 和轻量工具，MCP 提供外部服务集成。

### Q5: 技能激活会影响性能吗？

技能激活只是在 system prompt 中追加文本和注册额外工具，不会启动额外进程。对性能的影响极小。

---

**需要帮助？** 查看 [文档索引](README.md) 或提交 Issue！
