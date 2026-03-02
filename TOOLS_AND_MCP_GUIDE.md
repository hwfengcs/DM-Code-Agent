# 工具与 MCP 系统完整指南

## 1. 工具数据结构

### Tool（工具类）

```python
@dataclass
class Tool:
    """表示智能体可以调用的可调用工具"""
    
    name: str                                    # 工具名称
    description: str                             # 工具描述
    runner: Callable[[Dict[str, Any]], str]     # 工具执行函数
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行工具"""
        return self.runner(arguments)
```

**字段说明**：
- `name`：工具的唯一标识符（如 `read_file`、`write_file`）
- `description`：工具功能描述，包含参数说明
- `runner`：工具执行函数，接收参数字典，返回字符串结果

### 工具执行函数签名

```python
def tool_name(arguments: Dict[str, Any]) -> str:
    """
    工具执行函数
    
    Args:
        arguments: 工具参数字典
        
    Returns:
        str: 执行结果字符串
    """
    pass
```

### 参数验证辅助函数

```python
def _require_str(arguments: Dict[str[Any]], key: str) -> str:
    """
    从参数参数字典中提取必需的字符串参数
    
    Args:
        arguments: 包含参数的字典
        key: 要提取的参数键名
        
    Returns:
        去除首尾空白的字符串参数值
        
    Raises:
        ValueError: 当参数不符合要求时抛出异常
    """
```

**使用示例**：
```python
def my_tool(arguments: Dict[str, Any]) -> str:
    path = _require_str(arguments, "path")
    optional = arguments.get("optional", default_value)
    # ...
```

## 2. 内置工具

### 文件操作工具

```python
# 列出目录内容
Tool(
    name="list_directory",
    description="List entries for given directory path. Arguments: {\"path\": optional string (default '.'), \"recursive\": optional bool (default false), \"file_type\": optional string filter like '.py' or '.js'}.",
    runner=list_directory,
)

# 读取文件
Tool(
    name="read_file",
    description="Read a UTF-8 text file. Arguments: {\"path\": string, \"line_start\": optional int, \"line_end\": optional int}.",
    runner=read_file,
)

# 创建文件
Tool(
    name="create_file",
    description="Create or overwrite a text file. Arguments: {\"path\": string, \"content\": string}.",
    runner=create_file,
)

# 编辑文件
Tool(
    name="edit_file",
    description="Edit specific lines in a file. Arguments: {\"path\": string, \"operation\": \"insert\"|\"replace\"|\"delete\", \"line_start\": int, \"line_end\": int (for replace/delete), \"content\": string (for insert/replace)}.",
    runner=edit_file,
)

# 搜索文件内容
Tool(
    name="search_in_file",
    description="Search for text or regex pattern in a file. Arguments: {\"path\": string, \"pattern\": string, \"context_lines\": optional int (default 2)}.",
    runner=search_in_file,
)
```

### 执行工具

```python
# 执行 Python 代码
Tool(
    name="run_python",
    description="Execute Python code using local interpreter. Arguments: either {\"code\": string} or {\"path\": string, \"args\": optional string or list}.",
    runner=run_python,
)

# 执行 Shell 命令
Tool(
    name="run_shell",
    description="Execute a shell command. Arguments: {\"command\": string}.",
    runner=run_shell,
)

# 运行测试
Tool(
    name="run_tests",
    description="Run Python test suite. Arguments: {\"test_path\": optional string (default '.'), \"framework\": optional \"pytest\"|\"unittest\" (default 'pytest'), \"verbose\": optional bool (default false)}.",
    runner=run_tests,
)

# 运行代码检查工具
Tool(
    name="run_linter",
    description="Run code linter/formatter. Arguments: {\"path\": string, \"tool\": optional \"pylint\"|\"flake8\"|\"mypy\"|\"black\" (default 'flake8')}.",
    runner=run_linter,
)
```

### 代码分析工具

```python
# 解析 AST
Tool(
    name="parse_ast",
    description="Parse Python file AST to extract structure (functions, classes, imports). Arguments: {\"path\": string}.",
    runner=parse_ast,
)

# 获取函数签名
Tool(
    name="get_function_signature",
    description="Get function signature with type hints. Arguments: {\"path\": string, \"function_name\": string}.",
    runner=get_function_signature,
)

# 查找依赖
Tool(
    name="find_dependencies",
    description="Analyze file dependencies (imports). Arguments: {\"path\": string}.",
    runner=find_dependencies,
)

# 获取代码指标
Tool(
    name="get_code_metrics",
    description="Get code metrics (lines, functions, classes count). Arguments: {\"path\": string}.",
    runner=get_code_metrics,
)
```

### 任务完成工具

```python
def task_complete(arguments: Dict[str, Any]) -> str:
    """标记任务完成的工具"""
    message = arguments.get("message", "")
    if message and isinstance(message, str):
        return f"任务完成：{message.strip()}"
    return "任务已完成。"

Tool(
    name="task_complete",
    description="Mark task as complete and finish execution. Arguments: {\"message\": optional string with completion summary}.",
    runner=task_complete,
)
```

## 3. 工具执行流程

### 在 ReactAgent 中的执行

```python
class ReactAgent:
    def run(self, task: str, *, max_steps: Optional[int] = None) -> Dict[str, Any]:
        for step_num in range(1, limit + 1):
            # 1. 获取 AI 响应
            raw = self.client.respond(messages_to_send, temperature=self.temperature)
            parsed = self._parse_agent_response(raw)
            
            # 2. 解析动作和参数
            action = parsed.get("action", "").strip()
            action_input = parsed.get("action_input")
            
            # 3. 检查是否完成
            if action == "finish":
                return {"final_answer": final, "steps": steps}
            
            # 4. 查找工具
            tool = self.tools.get(action)
            if tool is None:
                observation = f"未知工具 '{action}'。"
                continue
            
            # 5. 执行工具
            try:
                observation = tool.execute(action_input)
            except Exception as exc:
                observation = f"工具执行失败：{exc}"
            
            # 6. 记录结果
            step = Step(
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
                raw=raw,
            )
            steps.append(step)
            
            # 7. 检查任务完成
            if action == "task_complete":
                return {"final_answer": observation, "steps": steps}
```

### 工具执行示例

```python
# 1. 定义工具
def read_file(arguments: Dict[str, Any]) -> str:
    path = _require_str(arguments, "path")
    line_start = arguments.get("line_start")
    line_end = arguments.get("line_end")
    
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    if line_start or line_end:
        start = line_start - 1 if line_start else 0
        end = line_end if line_end else len(lines)
        lines = lines[start:end]
    
    return "".join(lines)

# 2. 创建 Tool 对象
tool = Tool(
    name="read_file",
    description="Read a UTF-8 text file. Arguments: {\"path\": string, \"line_start\": optional int, \"line_end\": optional int}.",
    runner=read_file,
)

# 3. 执行工具
result = tool.execute({"path": "main.py", "line_start": 1, "line_end": 10})
```

## 4. MCP 系统数据结构

### MCPServerConfig（单个服务器配置）

```python
@dataclass
class MCPServerConfig:
    """表示单个 MCP 服务器的配置信息"""
    
    name: str                                # 服务器名称
    command: str                              # 启动命令
    args: List[str] = field(default_factory=list)  # 命令行参数
    env: Optional[Dict[str, str]] = None     # 环境变量
    enabled: bool = True                     # 是否启用
    
    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "MCPServerConfig":
        """从字典数据创建配置"""
        return cls(
            name=name,
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env"),
            enabled=data.get("enabled", True)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        result = {
            "command": self.command,
            "args": self.args,
        }
        if self.env:
            result["env"] = self.env
        if not self.enabled:
            result["enabled"] = self.enabled
        return result
```

### MCPConfig（总配置）

```python
@dataclass
class MCPConfig:
    """管理所有 MCP 服务器的配置集合"""
    
    servers: Dict[str, MCPServerConfig] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPConfig":
        """从字典数据创建配置"""
        mcp_servers = data.get("mcpServers", {})
        servers = {
            name: MCPServerConfig.from_dict(name, config)
            for name, config in mcp_servers.items()
        }
        return cls(servers=servers)
    
    def to_dict(self) -> Dict[str, Any]:
        """将总配置转换为字典"""
        return {
            "mcpServers": {
                name: config.to_dict()
                for name, config in self.servers.items()
            }
        }
    
    def add_server(self, config: MCPServerConfig) -> None:
        """添加服务器配置"""
        self.servers[config.name] = config
    
    def remove_server(self, name: str) -> None:
        """移除服务器配置"""
        if name in self.servers:
            del self.servers[name]
    
    def get_enabled_servers(self) -> Dict[str, MCPServerConfig]:
        """获取所有启用的服务器配置"""
        return {
            name: config
            for name, config in self.servers.items()
            if config.enabled
        }
```

### MCPClient（MCP 客户端）

```python
class MCPClient:
    """MCP 客户端 - 负责与单个 MCP 服务器通信"""
    
    def __init__(
        self, 
        name: str, 
        command: str, 
        args: List[str], 
        env: Optional[Dict[str, str]] = None
    ):
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.process: Optional[subprocess.Popen] = None
        self.tools: List[Dict[str, Any]] = []
        self._lock = Lock()
        self._message_id = 0
        self._stdout_queue: Queue = Queue()
        self._running = False
```

**核心方法**：
- `start()`：启动 MCP 服务器进程
- `stop()`：停止 MCP 服务器进程
- `call_tool(tool_name, arguments)`：调用 MCP 工具
- `get_tools()`：获取服务器提供的工具列表
- `is_running()`：检查服务器是否运行中

### MCPManager（MCP 管理器）

```python
class MCPManager:
    """MCP 管理器 - 统一管理多个 MCP 服务器"""
    
    def __init__(self, config: Optional[MCPConfig] = None):
        self.config = config or MCPConfig()
        self.clients: Dict[str, MCPClient] = {}
        self._tools_cache: List[Tool] = []
```

**核心方法**：
- `start_all()`：启动所有启用的服务器
- `start_server(name)`：启动指定服务器
- `stop_server(name)`：停止指定服务器
- `stop_all()`：停止所有服务器
- `get_tools()`：获取所有 MCP 工具
- `get_running_servers()`：获取运行中的服务器列表
- `get_server_status()`：获取所有服务器状态

## 5. MCP 配置文件

### 配置文件格式（mcp_config.json）

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
      "args": ["@modelcontextprotocol/server-filesystem", "/path/to/allowed"],
      "enabled": true
    },
    "github": {
      "command": "npx",
      "args": ["@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "your-token"
      },
      "enabled": false
    }
  }
}
```

### 加载和保存配置

```python
from dm_agent.mcp import load_mcp_config, save_mcp_config

# 加载配置
config = load_mcp_config("mcp_config.json")

# 保存配置
save_mcp_config(config, "mcp_config.json")
```

## 6. MCP 服务器管理

### 启动服务器

```python
# 1. 创建管理器
manager = MCPManager(config)

# 2. 启动所有服务器
started_count = manager.start_all()
print(f"成功启动 {started_count} 个服务器")

# 3. 启动单个服务器
success = manager.start_server("playwright")
if success:
    print("服务器启动成功")
```

### 停止服务器

```python
# 停止单个服务器
manager.stop_server("playwright")

# 停止所有服务器
manager.stop_all()
```

### 查询服务器状态

```python
# 获取运行中的服务器
running = manager.get_running_servers()
print(f"运行中的服务器: {running}")

# 获取所有服务器状态
status = manager.get_server_status()
for name, is_running in status.items():
    print(f"{name}: {'运行中' if is_running else '已停止'}")
```

## 7. MCP 工具集成

### 工具缓存机制

```python
def _rebuild_tools_cache(self) -> None:
    """重建工具缓存"""
    self._tools_cache.clear()
    
    for server_name, client in self.clients.items():
        if not client.is_running():
            continue
        
        mcp_tools = client.get_tools()
        for tool_def in mcp_tools:
            # 将 MCP 工具转换为 Tool 对象
            wrapped_tool = self._create_tool_wrapper(
                server_name=server_name,
                tool_name=tool_def.get("name", ""),
                description=tool_def.get("description", ""),
                input_schema=tool_def.get("inputSchema", {})
            )
            self._tools_cache.append(wrapped_tool)
```

### 工具包装器

```python
def _create_tool_wrapper(
    self,
    server_name: str,
    tool_name: str,
    description: str,
    input_schema: Dict[str, Any]
) -> Tool:
    """创建 MCP 工具的包装器"""
    
    # 构建完整的工具描述
    full_description = f"[MCP:{server_name}] {description}"
    
    # 添加参数信息
    if input_schema and "properties" in input_schema:
        properties = input_schema["properties"]
        required = input_schema.get("required", [])
        
        params_desc = []
        for param_name, param_info in properties.items():
            param_type = param_info.get("type", "any")
            param_desc = param_info.get("description", "")
            is_required = param_name in required
            
            param_str = f'"{param_name}": {param_type}'
            if not is_required:
                param_str = f"optional {param_str}"
            if param_desc:
                param_str += f" ({param_desc})"
            
            params_desc.append(param_str)
        
        if params_desc:
            full_description += f". Arguments: {{{', '.join(params_desc)}}}"
    
    # 创建工具执行函数
    def runner(arguments: Dict[str, Any]) -> str:
        client = self.clients.get(server_name)
        if not client or not client.is_running():
            return f"❌ MCP 服务器 '{server_name}' 未运行"
        
        result = client.call_tool(tool_name, arguments)
        if result is None:
            return f"❌ 调用 MCP 工具 '{tool_name}' 失败"
        
        return result
    
    return Tool(
        name=f"mcp_{server_name}_{tool_name}",
        description=full_description,
        runner=runner
    )
```

### 获取 MCP 工具

```python
# 获取所有 MCP 工具
mcp_tools = manager.get_tools()

# 与默认工具合并
from dm_agent.tools import default_tools
tools = default_tools(include_mcp=True, mcp_tools=mcp_tools)

# 创建 Agent
agent = ReactAgent(client, tools)
```

## 8. MCP 客户端通信

### JSON-RPC 通信协议

```python
def _send_message(
    self, 
    method: str, 
    params: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """发送 JSON-RPC 消息到 MCP 服务器"""
    
    with self._lock:
        self._message_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": self._message_id,
            "method": method,
        }
        if params:
            message["params"] = params
        
        # 发送消息
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        
        # 等待响应
        timeout_count = 0
        while timeout_count < 50:  # 5 秒超时
            try:
                response_line = self._stdout_queue.get(timeout=0.1)
                response = json.loads(response_line)
                
                if response.get("id") == self._message_id:
                    if "error" in response:
                        return None
                    return response.get("result")
                
                self._stdout_queue.put(response_line)
            except Empty:
                timeout_count += 1
        
        return None
```

### 初始化连接

```python
def _initialize(self) -> bool:
    """初始化 MCP 连接并获取工具列表"""
    
    # 发送初始化请求
    result = self._send_message("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {
            "name": "dm-code-agent",
            "version": "1.1.0"
        }
    })
    
    if not result:
        return False
    
    # 获取工具列表
    tools_result = self._send_message("tools/list")
    if tools_result and "tools" in tools_result:
        self.tools = tools_result["tools"]
        return True
    
    return False
```

### 调用工具

```python
def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
    """调用 MCP 工具"""
    
    result = self._send_message("tools/call", {
        "name": tool_name,
        "arguments": arguments
    })
    
    if result and "content" in result:
        content = result["content"]
        if isinstance(content, list) and len(content) > 0:
            first_item = content[0]
            if isinstance(first_item, dict) and "text" in first_item:
                return first_item["text"]
            return str(first_item)
        return str(content)
    
    return None
```

## 9. 完整使用示例

### 配置和使用 MCP

```python
from dm_agent.mcp import MCPManager, load_mcp_config
from dm_agent.tools import default_tools
from dm_agent.core import ReactAgent

# 1. 加载 MCP 配置
mcp_config = load_mcp_config("mcp_config.json")

# 2. 创建 MCP 管理器
mcp_manager = MCPManager(mcp_config)

# 3. 启动所有 MCP 服务器
started = mcp_manager.start_all()
print(f"启动了 {started} 个 MCP 服务器")

# 4. 获取 MCP 工具
mcp_tools = mcp_manager.get_tools()
print(f"获取到 {len(mcp_tools)} 个 MCP 工具")

# 5. 合并工具
tools = default_tools(include_mcp=True, mcp_tools=mcp_tools)

# 6. 创建 Agent
agent = ReactAgent(client, tools)

# 7. 执行任务
result = agent.run("使用 Playwright 自动化测试网页")

# 8. 清理
mcp_manager.stop_all()
```

### 动态添加 MCP 服务器

```python
from dm_agent.mcp import MCPManager, MCPServerConfig

# 创建管理器
manager = MCPManager()

# 添加服务器配置
config = MCPServerConfig(
    name="playwright",
    command="npx",
    args=["@playwright/mcp"],
    enabled=True
)
manager.add_server_config(config)

# 启动服务器
manager.start_server("playwright")

# 获取工具
tools = manager.get_tools()
```

## 10. 最佳实践

### 工具开发建议

1. **清晰的描述**：工具描述应包含参数说明和示例
2. **参数验证**：使用 `_require_str` 验证必需参数
3. **错误处理**：捕获异常并返回友好的错误消息
4. **返回格式**：统一返回字符串格式

### MCP 配置建议

1. **按需启用**：只启用需要的 MCP 服务器
2. **环境变量**：敏感信息通过环境变量传递
3. **路径配置**：使用绝对路径避免路径问题
4. **错误处理**：处理服务器启动失败的情况

### 性能优化

1. **工具缓存**：MCP 管理器自动缓存工具列表
2. **按需启动**：只启动需要的 MCP 服务器
3. **及时清理**：任务完成后停止不需要的服务器
4. **超时控制**：合理设置 MCP 通信超时
