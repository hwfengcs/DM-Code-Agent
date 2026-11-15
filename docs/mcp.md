# MCP 配置

MCP（Model Context Protocol）服务器给 agent 提供额外工具。配置文件是当前工作目录下的
`mcp_config.json`，独立于 `config.json` 与 CLI 参数。

## 快速开始

### 1. 准备工作

确保你已经安装了 Node.js 和 npm（因为大部分 MCP 服务器使用 Node.js 运行）：

```bash
# 检查是否已安装
node --version
npm --version
```

### 2. 配置 Playwright MCP

仓库提供 `mcp_config.json.example`，复制为 `mcp_config.json` 后按需启用服务器。
例如仅配置 Playwright：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest"
      ],
      "enabled": true
    }
  }
}
```

### 3. 启动系统

运行 Agent 系统，MCP 服务器会自动启动：

```bash
python main.py
```

你将会看到类似输出：

```
  RUN    正在加载 MCP 服务器
✅ MCP 服务器 'playwright' 启动成功，提供 5 个工具
  DONE   成功启动 1 个 MCP 服务器
  DONE   加载了 5 个 MCP 工具
```

---

## Playwright MCP 使用示例

工具通过服务器的 `tools/list` 动态发现，名称自动加上 `mcp_playwright_` 前缀。
导航、截图、点击和表单操作的具体名称与数量以启动后菜单中的工具列表为准。

## Context7 MCP 使用示例 ⭐ 新增

Context7 提供第三方库文档检索，不是项目历史或记忆存储服务。
工具通过 `tools/list` 动态发现，名称自动加上 `mcp_context7_` 前缀。

### Context7 配置说明

安装、认证与当前工具说明见 <https://github.com/upstash/context7>。
基础 stdio 配置如下；如需认证，按该服务器文档设置，不能把 Upstash 数据库 key 当作
Context7 的通用认证参数。

**配置示例**：
```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"],
      "enabled": true
    }
  }
}
```

### 示例任务

#### 示例 1：Playwright - 打开网页并截图

```bash
python main.py "打开 https://www.example.com 并截图保存为 example.png"
```

Agent 会自动调用 Playwright MCP 工具来完成任务。

#### 示例 2：Playwright - 自动化表单填写

```
"打开 https://example.com/login，在用户名框中输入 'testuser'，在密码框中输入 'password123'，然后点击登录按钮"
```

#### 示例 3：Playwright - 网页数据提取

```
"访问 https://news.ycombinator.com，提取前 10 条新闻标题"
```

#### 示例 4：Context7 - 查找库文档

```bash
python main.py "用 Context7 查找 FastAPI 的依赖注入文档"
```

#### 示例 5：Context7 - 核对 API 用法

```bash
python main.py "用 Context7 核对当前 React 版本的 useEffect 清理函数用法"
```

#### 示例 6：Context7 - 检索库示例

```bash
python main.py "从 Context7 获取 SQLAlchemy 的事务管理示例"
```

---

## 如何接入新的 MCP 服务器

### 方法 1：通过配置文件接入（推荐）

这是最简单的方法，适用于大部分场景。

#### 步骤 1：获取 MCP 服务器的配置信息

每个 MCP 服务器都会提供一个 JSON 配置，通常包含：

- `command`: 启动命令（如 `npx`, `node`, `python`）
- `args`: 命令参数列表
- `env`: 环境变量（可选）
- `timeout`: 单次 JSON-RPC 请求（初始化握手、`tools/list` 与每次工具调用各算一次）的超时秒数（可选，默认 5；慢速服务器如浏览器自动化可调大）

服务器进程意外退出时，agent 在下一次工具调用会自动做一次重连；仍失败才把错误反馈给模型。

**示例**：假设你找到了一个新的 MCP 服务器，它的配置如下：

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem@latest"]
}
```

#### 步骤 2：添加到 `mcp_config.json`

编辑项目根目录下的 `mcp_config.json` 文件，在 `mcpServers` 中添加新服务器：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"],
      "enabled": true
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem@latest"],
      "enabled": true
    }
  }
}
```

#### 步骤 3：重启 Agent 系统

```bash
python main.py
```

系统会自动加载新的 MCP 服务器！

### 方法 2：带环境变量的 MCP 服务器

某些 MCP 服务器需要环境变量（如 API 密钥）：

```json
{
  "mcpServers": {
    "weather-api": {
      "command": "node",
      "args": ["/path/to/weather-mcp-server.js"],
      "env": {
        "WEATHER_API_KEY": "your_api_key_here",
        "DEBUG": "true"
      },
      "enabled": true
    }
  }
}
```

### 方法 3：本地开发的 MCP 服务器

如果你自己开发了一个 MCP 服务器：

```json
{
  "mcpServers": {
    "my-custom-server": {
      "command": "python",
      "args": ["/absolute/path/to/my_mcp_server.py"],
      "enabled": true
    }
  }
}
```

---

## MCP 配置详解

### 配置文件结构

```json
{
  "mcpServers": {
    "<服务器名称>": {
      "command": "<启动命令>",
      "args": ["<参数1>", "<参数2>"],
      "env": {
        "<环境变量名>": "<环境变量值>"
      },
      "enabled": true
    }
  }
}
```

### 字段说明

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `command` | ✅ | 启动命令 | `"npx"`, `"node"`, `"python"` |
| `args` | ❌ | 命令参数列表，默认空列表 | `["@playwright/mcp@latest"]` |
| `env` | ❌ | 环境变量字典 | `{"API_KEY": "xxx"}` |
| `enabled` | ❌ | 是否启用（默认 `true`） | `true` 或 `false` |
| `timeout` | ❌ | 单次请求超时秒数，默认 `5` | `30` |

### 禁用某个 MCP 服务器

临时禁用某个服务器而不删除配置：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"],
      "enabled": false
    }
  }
}
```

---

## 常见 MCP 服务器推荐

以下配置块是 `mcpServers` 内的服务器映射，需放入完整文件的 `mcpServers` 对象中。
Filesystem 的参数还需添加允许访问的工作区绝对路径；各外部包的安装与认证参数以其文档为准。

### 1. Playwright（浏览器自动化）

```json
{
  "playwright": {
    "command": "npx",
    "args": ["@playwright/mcp@latest"],
    "enabled": true
  }
}
```

**用途**：网页自动化、截图、表单填写、数据爬取

### 2. Context7（第三方库文档检索）

```json
{
  "context7": {
    "command": "npx",
    "args": ["-y", "@upstash/context7-mcp"],
    "enabled": true
  }
}
```

**用途**：查找第三方库的文档、API 用法和示例

**安装与认证说明**：https://github.com/upstash/context7

### 3. Filesystem（文件系统操作）

```json
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem@latest"],
    "enabled": true
  }
}
```

**用途**：高级文件操作、目录遍历、文件监控

### 4. Puppeteer（浏览器自动化）

```json
{
  "puppeteer": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-puppeteer@latest"],
    "enabled": true
  }
}
```

**用途**：与 Playwright 类似，但使用 Puppeteer 引擎

### 5. SQLite（数据库操作）

```json
{
  "sqlite": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-sqlite@latest"],
    "enabled": true
  }
}
```

**用途**：SQLite 数据库查询和管理

---

## 实战示例：接入新的 MCP 服务器

### 场景：接入 GitHub MCP 服务器

假设有一个 GitHub MCP 服务器，配置如下：

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-github@latest"],
  "env": {
    "GITHUB_TOKEN": "ghp_your_token_here"
  }
}
```

**步骤**：

1. **获取 GitHub Token**
   访问 https://github.com/settings/tokens 生成一个 Personal Access Token

2. **编辑 `mcp_config.json`**

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"],
      "enabled": true
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github@latest"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      },
      "enabled": true
    }
  }
}
```

3. **启动系统**

```bash
python main.py
```

4. **使用 GitHub MCP 工具**

```
"列出我的 GitHub 仓库中所有 Python 项目"
```

Agent 会自动调用 GitHub MCP 工具来完成任务！

---

## 常见问题

### Q1: MCP 服务器启动失败怎么办？

**可能原因**：
1. Node.js 未安装或版本过低
2. 网络问题，无法下载 MCP 包
3. 配置文件格式错误

**解决方法**：
```bash
# 检查 Node.js
node --version  # 版本需满足所选 MCP 包的 engines 要求

# 手动安装 MCP 包
npx @playwright/mcp@latest

# 检查配置文件
python -c "import json; json.load(open('mcp_config.json'))"
```

### Q2: 如何查看 MCP 服务器提供了哪些工具？

启动系统后，选择菜单选项 `3. 查看可用工具列表`，所有 MCP 工具会显示为 `mcp_<服务器名>_<工具名>` 格式。

### Q3: 能否在命令行模式使用 MCP 工具？

可以！MCP 工具在交互模式和命令行模式都可用：

```bash
python main.py "使用 Playwright 打开 https://example.com 并截图"
```

### Q4: MCP 服务器会占用很多资源吗？

MCP 服务器是独立进程，所有启用的服务器都会在系统启动时一并启动。如果不需要某个服务器，可以在配置中设置 `"enabled": false`。

### Q5: 如何调试 MCP 服务器？

MCP 客户端会输出详细的错误信息。你也可以手动测试 MCP 服务器：

```bash
# 手动启动 MCP 服务器
npx @playwright/mcp@latest

# 查看输出
```


---

**需要帮助？** 查看 [文档索引](README.md) 或提交 Issue！
