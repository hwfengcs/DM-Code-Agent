# 你的第一个AI Agent项目

<div align="center">

**基于多种 LLM API 的智能 Code Agent（代码智能体）**

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**中文** | [English](README_EN.md)

</div>

## 📖 项目简介
如果你刚刚开始学习AI Agent却无从入手，请从我的这个项目开始学习或者开发你自己Agent应用。

本项目为所有新学习AI Agent的开发者提供了一个上手学习难度极低，但是功能强大的 **Code Agent（代码智能体）**，基于 ReAct（Reasoning + Acting）架构，支持多种大语言模型（DeepSeek、OpenAI、Claude、Gemini）进行推理，专注于软件开发和代码相关任务。

**⭐ v1.3.0 新增：现代化 Web 界面！** - 提供美观的 Next.js + Flask 前后端分离架构，支持实时对话、可视化配置、工具管理等功能。

### 🎯 核心能力
- 📋 **任务规划** - 执行前生成结构化计划，减少无效操作 30-50% (v1.1.0)
- 🧠 **代码分析** - 解析 AST、提取函数签名、分析依赖关系 (v1.1.0)
- 🗜️ **上下文压缩** - 自动压缩对话历史，支持长对话不超限 (v1.1.0)
- 🔌 **MCP 协议支持** - 接入任意 MCP 工具，无限扩展能力 (v1.2.0)
- 🌐 **现代化 Web 界面** - Next.js + Flask 架构，实时通信，美观易用 (v1.3.0) ⭐ 新增

### 🛠️ 工具能力
- 📝 **代码编辑** - 精确编辑文件指定行，支持插入/替换/删除
- 🔍 **代码搜索** - 正则表达式搜索，带上下文显示
- 🧪 **测试执行** - 运行 pytest/unittest 测试套件
- ✨ **代码检查** - 运行 pylint/flake8/mypy/black 检查工具
- 📁 **文件操作** - 创建、读取（支持行范围）、列出文件和目录（支持递归过滤）
- 🐍 **Python 执行** - 运行 Python 代码和脚本
- 💻 **Shell 命令** - 执行系统命令
- 🎯 **任务完成** - 智能标记任务完成状态
- 🎨 **交互式界面** - 友好的菜单式操作体验

## ✨ 主要特性

### 🎯 v1.1.0 新增核心功能
#### 📋 任务规划器（Task Planner）
- **智能计划生成** - 任务执行前自动生成 3-8 步结构化计划
- **实时进度跟踪** - 标记完成的步骤，清晰展示执行进度
- **效率提升 30-50%** - 减少无效工具调用，提高任务成功率
- **自动回退机制** - 计划生成失败时自动切换到常规模式

#### 🧠 代码分析工具（Code Analysis Tools）
- **parse_ast** - 解析 Python 文件 AST，提取函数、类、导入等结构信息
- **get_function_signature** - 获取函数完整签名和类型注解
- **find_dependencies** - 分析文件依赖关系（标准库、第三方库、本地模块）
- **get_code_metrics** - 统计代码行数、函数数、类数等度量指标

#### 🗜️ 上下文压缩器（Context Compressor）
- **自动压缩** - 每 5 轮对话自动压缩历史，保留最近 3 轮完整对话
- **智能摘要** - 提取关键信息（文件路径、工具调用、错误、完成任务）
- **节省 Token** - 减少 20-30% token 消耗，支持更长的对话
- **无缝集成** - 全自动，无需手动干预

#### 🔌 MCP 协议集成（Model Context Protocol）⭐ v1.2.0 新增
- **零代码扩展** - 通过配置文件接入任意 MCP 工具，无需修改代码
- **预置 Playwright** - 内置浏览器自动化能力（导航、截图、点击、填表）
- **预置 Context7** - 智能上下文管理和语义搜索
- **统一工具接口** - MCP 工具自动包装为标准 Tool 对象
- **生命周期管理** - 自动启动和停止 MCP 服务器进程
- **常见 MCP 支持** - Playwright、Context7、Filesystem、SQLite 等
- **详细文档** - 参见 [MCP_GUIDE.md](MCP_GUIDE.md) 获取完整接入指南

### 🤖 多模型支持
- **DeepSeek** - 默认模型，性价比高
- **OpenAI** - GPT-3.5/GPT-4 系列模型
- **Claude** - Anthropic Claude 3.5 系列
- **Gemini** - Google Gemini 系列
- 支持自定义 Base URL 和模型参数

### 🚀 交互式 CLI 界面
- **友好的菜单系统** - 无需记忆复杂命令
- **实时配置调整** - 动态修改运行参数
- **彩色输出** - 清晰美观的界面（支持 colorama）
- **工具列表查看** - 一键查看所有可用工具

### 🛠️ 强大的 Code Agent 工具集

**MCP 工具** ⭐ v1.2.0 新增
- `mcp_playwright_*` - 浏览器自动化工具（导航、截图、点击、表单）
- `mcp_context7_*` - 智能上下文管理工具（存储、检索、搜索）
- 支持动态加载任意 MCP 工具

**代码分析工具** (v1.1.0)
- `parse_ast` - 解析 Python 文件 AST 结构
- `get_function_signature` - 提取函数签名和类型
- `find_dependencies` - 分析文件依赖关系
- `get_code_metrics` - 获取代码度量指标

**代码编辑工具**
- `edit_file` - 精确编辑文件指定行（插入/替换/删除）
- `search_in_file` - 正则表达式搜索，带上下文显示

**测试和检查工具**
- `run_tests` - 运行 pytest/unittest 测试套件
- `run_linter` - 运行 pylint/flake8/mypy/black 代码检查

**文件操作工具**
- `list_directory` - 列出目录内容（支持递归和类型过滤）
- `read_file` - 读取文本文件（支持行号范围）
- `create_file` - 创建或覆盖文件

**代码执行工具**
- `run_python` - 执行 Python 代码
- `run_shell` - 执行 Shell 命令
- `task_complete` - 标记任务完成

### 🎯 灵活的使用方式
- **Web 界面模式** - 现代化图形界面，实时交互体验 ⭐ v1.3.0 新增
- **CLI 交互模式** - 菜单式操作，适合连续任务
- **多轮对话模式** - 持续对话，记住完整历史
- **命令行模式** - 快速执行单个任务
- **批处理模式** - 支持脚本自动化
- **持久化配置** - 自定义配置永久保存

## 📋 前置要求

- **Python 3.7+** （推荐 3.9 或更高版本）
- **LLM API 密钥** - 根据使用的模型选择：
  - [DeepSeek API 密钥](https://platform.deepseek.com/)（默认）
  - [OpenAI API 密钥](https://platform.openai.com/)
  - [Claude API 密钥](https://console.anthropic.com/)
  - [Gemini API 密钥](https://makersuite.google.com/app/apikey)

## 🔧 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd dm-agent
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

**依赖包说明**：
- `requests` - HTTP 请求库，用于调用 LLM API
- `python-dotenv` - 环境变量管理
- `colorama` - 彩色终端输出（可选但推荐）
- `google-generativeai` - Google Gemini 官方 SDK

### 3. 配置 API 密钥

复制 `.env.example` 文件并重命名为 `.env`，然后添加你的真实 API 密钥：

```bash
# 复制示例文件
cp .env.example .env

# 编辑 .env 文件，根据使用的模型配置对应的密钥
# DeepSeek（默认）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# OpenAI（可选）
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# Claude（可选）
CLAUDE_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx

# Gemini（可选）
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
```

**⚠️ 安全提醒**：
- `.env` 文件包含你的私密 API 密钥，已在 `.gitignore` 中配置，不会被提交到 Git
- 请勿将 `.env` 文件分享给他人或上传到公共仓库
- 只有 `.env.example` 文件会被提交到仓库作为配置模板

或者在命令行中设置环境变量：

**Windows (PowerShell)**:
```powershell
$env:DEEPSEEK_API_KEY="your_api_key_here"
```

**Linux/macOS**:
```bash
export DEEPSEEK_API_KEY="your_api_key_here"
```

## 🚀 快速开始

### 🌐 Web 界面模式（推荐）⭐ v1.3.0 新增

提供现代化的图形界面，支持实时对话、可视化配置等功能。

#### 第一次使用需要安装前端依赖：

```bash
# 进入前端目录
cd frontend

# 安装依赖（需要 Node.js 16+）
npm install
```

#### 启动系统：

**1. 启动后端服务器**（在项目根目录）：
```bash
python app.py
```

**2. 启动前端界面**（新开终端窗口，在 frontend 目录）：
```bash
cd frontend
npm run dev
```

**3. 访问 Web 界面**：
打开浏览器访问 **http://localhost:3000**


#### 🖥️ 界面特性速览（持续迭代中）
- **两栏响应式布局**：在 1920px 及以上屏幕自动铺满，左侧专注输入/计划，右侧聚合状态与日志。
- **卡片内滚动**：执行计划、运行状态、运行日志默认固定高度，内容超出时在卡片内滚动，保证首屏信息稳定。
- **长回复折叠**：当 AI 回复超过 600 字或 12 行时自动折叠，点击“展开全部/收起内容”即可切换，阅读更轻松。
- **渐变与呼吸动画**：重要状态配合渐变背景与呼吸灯提示，帮助快速判断 Agent 进度。

---

### 💻 CLI 交互模式

直接运行程序进入友好的菜单界面：

```bash
python main.py
```

你会看到：

```
======================================================================
              DM-Agent 智能体系统
======================================================================
欢迎使用多模型 ReAct 智能体系统！

主菜单：
  1. 执行新任务
  2. 多轮对话模式
  3. 查看可用工具列表
  4. 配置设置
  5. 退出程序

请选择操作 (1-5):
```

### 命令行模式（快速执行）

直接在命令行中执行任务：

```bash
# 基本用法（使用默认的 DeepSeek）
python main.py "创建一个打印 hello world 的 hello.py 文件"

# 使用 OpenAI
python main.py "你的任务" --provider openai --model gpt-4

# 使用 Claude
python main.py "你的任务" --provider claude --model claude-3-5-sonnet-20241022

# 使用 Gemini
python main.py "你的任务" --provider gemini --model gemini-1.5-flash

# 显示详细步骤
python main.py "计算 123 + 456" --show-steps

# 自定义配置
python main.py "你的任务" --max-steps 50 --temperature 0.5
```

## 📚 使用示例

#### 任务规划器示例
```bash
python main.py "创建一个完整的计算器程序，包括加减乘除功能和测试"
```

执行时会看到：
```
📋 生成的执行计划：
计划进度：0/5 步骤已完成

○ 步骤 1: create_file - 创建计算器主程序文件
○ 步骤 2: edit_file - 添加计算函数
○ 步骤 3: create_file - 创建测试文件
○ 步骤 4: run_tests - 运行测试验证
○ 步骤 5: task_complete - 完成任务
```

#### 代码分析工具示例
```bash
# 分析文件结构
python main.py "分析 main.py 的代码结构，列出所有函数和类"

# 提取函数签名
python main.py "获取 calculator.py 中 calculate 函数的完整签名"

# 分析依赖关系
python main.py "分析 main.py 依赖了哪些第三方库"

# 获取代码度量
python main.py "统计 src 目录下所有 Python 文件的代码行数"
```

#### 上下文压缩示例
在多轮对话模式下，每 5 轮会自动压缩：
```
🗜️ 压缩对话历史以节省 token...
   压缩率：62.5%，节省 10 条消息
```

### 示例 0.5: MCP 工具使用 ⭐ v1.2.0

#### Playwright MCP 示例（浏览器自动化）
```bash
# 打开网页并截图
python main.py "打开 https://www.example.com 并截图保存为 example.png"

# 自动化表单填写
python main.py "打开 https://example.com/login，在用户名框输入 'testuser'，密码框输入 'password123'，然后点击登录"

# 网页数据提取
python main.py "访问 https://news.ycombinator.com 并提取前 10 条新闻标题"
```

#### Context7 MCP 示例（上下文管理）
```bash
# 存储上下文
python main.py "将当前项目的架构信息存储到 Context7"

# 语义搜索
python main.py "在 Context7 中搜索与数据库相关的上下文"

# 关联上下文
python main.py "获取与当前任务相关的历史上下文"
```

#### 接入新的 MCP 工具
只需 3 步，无需代码：
1. 编辑 `mcp_config.json` 添加配置
2. 重启系统
3. 工具自动可用

详见：[MCP_GUIDE.md](MCP_GUIDE.md)

### 示例 1: 代码编辑
```bash
# 在指定行插入代码
python main.py "在 test.py 的第 10 行插入一个打印语句"

# 替换指定行范围的代码
python main.py "替换 main.py 的第 5-8 行为新的函数实现"

# 搜索并修改代码
python main.py "在项目中搜索所有包含 'TODO' 的代码并列出"
```

### 示例 2: 测试和代码检查 ⭐ 新功能
```bash
# 运行测试
python main.py "运行 tests 目录下的所有测试用例"

# 代码检查
python main.py "用 flake8 检查 src 目录下的代码质量"

# 格式化检查
python main.py "检查 main.py 是否符合 black 代码风格"
```

### 示例 3: 文件操作（增强功能）
```bash
# 读取指定行范围
python main.py "读取 config.py 的第 10-20 行"

# 递归列出 Python 文件
python main.py "列出项目中所有的 .py 文件"

# 创建文件
python main.py "创建一个名为 notes.txt 的文件，内容为今天的日期"
```

### 示例 4: 数学计算

```bash
python main.py "计算 (100 + 200) * 3 的结果" --show-steps
```

### 示例 5: 代码执行

```bash
python main.py "使用 Python 生成 10 个随机数并保存到 random.txt"
```

### 示例 6: 复杂任务

```bash
python main.py "帮我创建一个 sort 文件夹，里面写 10 种排序算法的 cpp 代码和 py 代码"
```

### 示例 7: 多轮对话 ⭐ 新增

```bash
python main.py
# 选择选项 2: 多轮对话模式
# 对话 1: "创建一个 test.py 文件"
# 对话 2: "在刚才的文件中写入一个打印 Hello 的函数"
# 对话 3: "运行那个文件"
# 智能体会记住 test.py 的上下文
```

## ⚙️ 命令行参数

```
python main.py [任务] [选项]

位置参数:
  任务                  要执行的任务描述（可选）

可选参数:
  -h, --help           显示帮助信息
  --api-key KEY        API 密钥
  --provider PROVIDER  LLM 提供商（deepseek/openai/claude/gemini，默认：deepseek）⭐ 新增
  --model MODEL        模型名称（默认根据提供商自动选择）
  --base-url URL       API 基础 URL（可选，使用提供商默认值）⭐ 新增
  --max-steps N        最大步骤数（默认: 100）
  --temperature T      温度 0.0-2.0（默认: 0.7）
  --show-steps         显示执行步骤
  --interactive        强制进入交互模式
```

**注意**: 默认值可通过 `config.json` 永久修改

## 🎯 支持的模型

| 提供商 | 默认模型 | Base URL | 获取密钥 |
|--------|----------|----------|----------|
| **DeepSeek** | deepseek-chat | https://api.deepseek.com | [获取](https://platform.deepseek.com/) |
| **OpenAI** | gpt-3.5-turbo | https://api.openai.com | [获取](https://platform.openai.com/) |
| **Claude** | claude-3-5-sonnet-20241022 | https://api.anthropic.com | [获取](https://console.anthropic.com/) |
| **Gemini** | gemini-2.0-flash-exp | 使用官方 SDK | [获取](https://makersuite.google.com/) |

## 🎨 交互式菜单功能

### 1️⃣ 执行新任务
输入任务描述，智能体会自动执行并显示结果。每次都是全新的对话。

### 2️⃣ 多轮对话模式 ⭐ 新增
进入持续对话模式，智能体会记住所有历史对话和工具执行结果：
- 输入 `exit` 退出对话模式
- 输入 `reset` 重置对话历史
- 智能体会记住文件名、变量等上下文信息

### 3️⃣ 查看工具列表
查看所有可用工具及其功能描述。

### 4️⃣ 配置设置 ⭐ 已增强
动态调整运行参数并可选择永久保存：
- **LLM 提供商** (provider): deepseek/openai/claude/gemini ⭐ 新增
- **模型名称** (model): 根据提供商选择
- **Base URL** (base_url): API 基础 URL ⭐ 新增
- **最大步骤数** (max_steps): 1-200（默认：100）
- **温度** (temperature): 0.0-2.0（默认：0.7）
- **显示步骤** (show_steps): 是/否

修改后可选择保存到 `config.json`，下次启动自动加载。

### 5️⃣ 退出程序
安全退出应用。

## ⚙️ 配置管理

### 默认配置
- **LLM 提供商**: deepseek
- **模型**: deepseek-chat
- **Base URL**: https://api.deepseek.com
- **最大步骤数**: 100
- **温度**: 0.7
- **显示步骤**: 否

### 持久化配置
1. 启动程序并选择"配置设置"
2. 按提示修改参数（包括切换模型提供商）
3. 选择 `y` 保存为永久配置
4. 配置保存在 `config.json` 文件中

配置文件示例 (`config.json.example`)：
```json
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "base_url": "https://api.deepseek.com",
  "max_steps": 100,
  "temperature": 0.7,
  "show_steps": false
}
```

**注意**：
- Gemini 使用官方 Google SDK，不需要配置 `base_url`
- 其他提供商可以根据需要自定义 `base_url`（例如使用代理）

**提示**: `config.json` 已添加到 `.gitignore`，不会被提交到 git

## 🔄 项目结构

```
dm-code-agent/
├── main.py                         # CLI 程序入口（命令行界面）
├── app.py                          # Web 后端入口（Flask 服务器）⭐ v1.3.0 新增
├── check_mcp_env.py                # MCP 环境检查工具 (v1.2.0)
├── frontend/                       # Web 前端项目 ⭐ v1.3.0 新增
│   ├── app/                       # Next.js 页面
│   ├── components/                # React 组件
│   ├── lib/                       # 工具函数
│   ├── types/                     # TypeScript 类型
│   ├── package.json               # Node.js 依赖
│   └── ...配置文件
├── dm_agent/                       # 核心智能体包
│   ├── __init__.py                # 包初始化和公共 API
│   ├── core/                      # 核心 Agent 实现
│   │   ├── __init__.py
│   │   ├── agent.py              # ReactAgent 核心逻辑
│   │   └── planner.py            # 任务规划器 (v1.1.0)
│   ├── clients/                   # LLM 客户端
│   │   ├── __init__.py
│   │   ├── base_client.py        # 客户端基类
│   │   ├── deepseek_client.py    # DeepSeek 客户端
│   │   ├── openai_client.py      # OpenAI 客户端
│   │   ├── claude_client.py      # Claude 客户端
│   │   ├── gemini_client.py      # Gemini 客户端
│   │   └── llm_factory.py        # 客户端工厂
│   ├── mcp/                       # MCP 集成 (v1.2.0)
│   │   ├── __init__.py
│   │   ├── client.py             # MCP 客户端
│   │   ├── config.py             # MCP 配置管理
│   │   └── manager.py            # MCP 管理器
│   ├── memory/                    # 记忆和上下文管理 (v1.1.0)
│   │   ├── __init__.py
│   │   └── context_compressor.py # 上下文压缩器
│   ├── tools/                     # 工具集
│   │   ├── __init__.py
│   │   ├── base.py               # 工具基类
│   │   ├── file_tools.py         # 文件操作工具
│   │   ├── code_analysis_tools.py # 代码分析工具 (v1.1.0)
│   │   └── execution_tools.py    # 代码执行工具
│   └── prompts/                   # 提示词管理
│       ├── __init__.py
│       ├── system_prompts.py     # 提示词构建函数
│       └── code_agent_prompt.md  # 提示词模板
├── requirements.txt               # Python 依赖
├── .env.example                   # 环境变量配置模板
├── config.json.example            # 配置文件示例
├── mcp_config.json.example        # MCP 配置示例 (v1.2.0)
├── .gitignore                     # Git 忽略规则
├── WEB_SETUP.md                   # Web 界面启动指南 ⭐ v1.3.0 新增
├── DESIGN_DOC.md                  # 前端设计文档 ⭐ v1.3.0 新增
├── MCP_GUIDE.md                   # MCP 接入指南 (v1.2.0)
├── README.md                      # 中文说明文档
└── README_EN.md                   # 英文说明文档
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目采用 MIT 许可证。

**一起学习AI Agent吧！** 🚀
