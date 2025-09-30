# 你的第一个AI Agent项目

<div align="center">

**基于 DeepSeek API 的智能 ReAct（推理 + 行动）智能体**

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**中文** | [English](README_EN.md)

</div>

## 📖 项目简介
如果你刚刚开始学习AI Agent却无从入手，请从我的这个项目开始学习或者开发你自己Agent应用。

本项目为所有新学习AI Agent的开发者提供了一个上手学习难度极低，但是功能良好的 **ReAct（Reasoning + Acting）智能体**，使用 DeepSeek 大语言模型进行推理，并通过调用本地工具来完成各种任务。智能体可以：

- 📁 **文件操作** - 创建、读取、列出文件和目录
- 🐍 **Python 执行** - 运行 Python 代码和脚本
- 💻 **Shell 命令** - 执行系统命令
- 🎯 **任务完成** - 智能标记任务完成状态
- 🎨 **交互式界面** - 友好的菜单式操作体验

## ✨ 主要特性

### 🚀 交互式 CLI 界面
- **友好的菜单系统** - 无需记忆复杂命令
- **实时配置调整** - 动态修改运行参数
- **彩色输出** - 清晰美观的界面（支持 colorama）
- **工具列表查看** - 一键查看所有可用工具

### 🛠️ 强大的工具集
- `list_directory` - 列出目录内容
- `read_file` - 读取文本文件
- `create_file` - 创建或覆盖文件
- `run_python` - 执行 Python 代码
- `run_shell` - 执行 Shell 命令
- `task_complete` - 标记任务完成 ⭐ 新增

### 🎯 灵活的使用方式
- **交互模式** - 菜单式操作，适合连续任务
- **多轮对话模式** - 持续对话，记住完整历史
- **命令行模式** - 快速执行单个任务
- **批处理模式** - 支持脚本自动化
- **持久化配置** - 自定义配置永久保存 ⭐ 新增

## 📋 前置要求

- **Python 3.7+** （推荐 3.9 或更高版本）
- **DeepSeek API 密钥** - [获取 API 密钥](https://platform.deepseek.com/)

## 🔧 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd deepseek-react-agent
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

**依赖包说明**：
- `requests` - HTTP 请求库，用于调用 DeepSeek API
- `python-dotenv` - 环境变量管理
- `colorama` - 彩色终端输出（可选但推荐）

### 3. 配置 API 密钥

复制 `.env.example` 文件并重命名为 `.env`，然后添加你的真实 API 密钥：

```bash
# 复制示例文件
cp .env.example .env

# 编辑 .env 文件，将 your_api_key_here 替换为你的真实密钥
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
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

### 交互式模式（推荐）

直接运行程序进入友好的菜单界面：

```bash
python main.py
```

你会看到：

```
======================================================================
              DeepSeek ReAct 智能体
======================================================================
欢迎使用 DeepSeek 驱动的 ReAct 智能体系统！

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
# 基本用法
python main.py "创建一个打印 hello world 的 hello.py 文件"

# 显示详细步骤
python main.py "计算 123 + 456" --show-steps

# 自定义配置
python main.py "你的任务" --max-steps 50 --temperature 0.5
```

## 📚 使用示例

### 示例 1: 文件操作

```bash
python main.py "创建一个名为 notes.txt 的文件，内容为今天的日期"
```

### 示例 2: 数学计算

```bash
python main.py "计算 (100 + 200) * 3 的结果" --show-steps
```

### 示例 3: 代码执行

```bash
python main.py "使用 Python 生成 10 个随机数并保存到 random.txt"
```

### 示例 4: 复杂任务

```bash
python main.py "帮我创建一个 sort 文件夹，里面写 10 种排序算法的 cpp 代码和 py 代码"
```

### 示例 5: 多轮对话 ⭐ 新增

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
  --api-key KEY        DeepSeek API 密钥
  --model MODEL        模型名称（默认: deepseek-chat）
  --max-steps N        最大步骤数（默认: 100）⭐ 已更新
  --temperature T      温度 0.0-2.0（默认: 0.7）⭐ 已更新
  --show-steps         显示执行步骤
  --interactive        强制进入交互模式
```

**注意**: 默认值可通过 `config.json` 永久修改

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
- **最大步骤数** (max_steps): 1-200（默认：100）
- **温度** (temperature): 0.0-2.0（默认：0.7）
- **显示步骤** (show_steps): 是/否

修改后可选择保存到 `config.json`，下次启动自动加载。

### 5️⃣ 退出程序
安全退出应用。

## ⚙️ 配置管理

### 默认配置
- **最大步骤数**: 100
- **温度**: 0.7
- **显示步骤**: 否

### 持久化配置
1. 启动程序并选择"配置设置"
2. 按提示修改参数
3. 选择 `y` 保存为永久配置
4. 配置保存在 `config.json` 文件中

配置文件示例 (`config.json.example`)：
```json
{
  "model": "deepseek-chat",
  "max_steps": 100,
  "temperature": 0.7,
  "show_steps": false
}
```

**提示**: `config.json` 已添加到 `.gitignore`，不会被提交到 git

## 🛡️ 错误处理

程序会优雅地处理各种错误：

- ✅ API 密钥缺失 - 清晰的错误提示
- ✅ API 调用失败 - 显示错误详情
- ✅ 无效输入 - 输入验证和提示
- ✅ 键盘中断 - 可以随时 Ctrl+C 退出
- ✅ 文件操作错误 - 友好的错误消息

## 📖 更多文档

- **[README_CLI.md](README_CLI.md)** - 交互式 CLI 完整指南
- **[CLI_USAGE_EXAMPLES.md](CLI_USAGE_EXAMPLES.md)** - 详细使用示例
- **[CHANGELOG.md](CHANGELOG.md)** - 版本更新日志
- **[INSTALL_COLORAMA.md](INSTALL_COLORAMA.md)** - Colorama 安装说明

## 💡 提示和技巧

1. **连续任务** - 使用交互模式避免重复启动程序
2. **调试任务** - 使用 `--show-steps` 查看详细执行过程
3. **实验性任务** - 提高 temperature 值获得更有创意的结果
4. **复杂任务** - 增加 max-steps 允许更多推理步骤（默认已设为 50）
5. **快速测试** - 命令行模式适合脚本和自动化

## ❓ 常见问题

**Q: 如何获取 DeepSeek API 密钥？**
A: 访问 [DeepSeek 平台](https://platform.deepseek.com/) 注册并获取 API 密钥。

**Q: 如何退出交互模式？**
A: 选择菜单选项 4，或按 Ctrl+C。

**Q: 配置会保存吗？**
A: 配置仅在当前会话有效，重启后恢复默认值。

**Q: 必须安装 colorama 吗？**
A: 不必须，不安装也能正常使用，只是没有彩色输出。

**Q: 为什么任务显示"达到步骤限制但未完成"？**
A: 任务太复杂，需要更多步骤。可以通过 `--max-steps` 参数或在交互模式的配置设置中增加最大步骤数（默认已从 8 增加到 50）。

## 🔄 项目结构

```
deepseek-react-agent/
├── main.py                 # 主程序入口（交互式 CLI）
├── deepseek_agent/         # 核心智能体包
│   ├── __init__.py        # 包初始化
│   ├── agent.py           # ReactAgent 实现
│   ├── client.py          # DeepSeek API 客户端
│   └── tools.py           # 工具集定义
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量配置模板
├── .env                    # 你的私密配置（需自行创建，不会被提交）
├── config.json.example     # 配置文件示例
├── .gitignore             # Git 忽略规则
└── README.md              # 项目说明文档
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目采用 MIT 许可证。

## 🙏 致谢

- [DeepSeek](https://www.deepseek.com/) - 提供强大的 AI 模型
- [Colorama](https://github.com/tartley/colorama) - 跨平台彩色终端输出

---

**学习AI Agent吧！** 🚀
