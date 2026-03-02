# LLM 客户端架构分析

## 1. 数据结构

### 1.1 核心数据类型

**消息格式**
```python
List[Dict[str, str]]
```
- 每个消息包含 `role` 和 `content` 字段
- 支持的角色：`system`、`user`、`assistant`

**响应格式**
```python
Dict[str, Any]
```
- 各提供商返回不同的结构
- 通过 `extract_text()` 方法统一提取文本内容

### 1.2 类层次结构

```
BaseLLMClient (抽象基类)
├── DeepSeekClient
├── OpenAIClient
├── ClaudeClient
└── GeminiClient
```

**BaseLLMClient 字段**
- `api_key: str` - API 密钥
- `model: str` - 模型名称
- `base_url: str` - API 基础 URL
- `timeout: int` - 请求超时时间（秒）

**DeepSeekClient 特有字段**
- `endpoint: str` - API 端点路径
- `session: requests.Session` - HTTP 会话对象

**OpenAIClient 特有字段**
- `client: OpenAI` - 官方 SDK 客户端实例

**ClaudeClient 特有字段**
- `client: anthropic.Anthropic` - 官方 SDK 客户端实例
- `anthropic_version: str` - API 版本

**GeminiClient 特有字段**
- `client: genai.Client` - 官方 SDK 客户端实例

## 2. 生命周期管理

### 2.1 创建阶段

**工厂模式创建**
```python
# dm_agent/clients/llm_factory.py:14
def create_llm_client(
    provider: str,
    api_key: str,
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 600,
    **kwargs,
) -> BaseLLMClient
```

**初始化流程**
1. 验证 `api_key` 非空
2. 设置默认模型和 base_url
3. 初始化 SDK 客户端或 HTTP 会话
4. 配置认证头和超时

### 2.2 使用阶段

**核心方法调用链**
```
ReactAgent.run()
  └─> client.respond(messages, temperature)
       ├─> client.complete(messages, **extra)
       └─> client.extract_text(data)
```

**respond() 方法**
```python
# dm_agent/clients/base_client.py:60
def respond(self, messages: List[Dict[str, str]], **extra: Any) -> str:
    data = self.complete(messages, **extra)
    return self.extract_text(data)
```

### 2.3 销毁阶段

- 客户端对象在 ReactAgent 销毁时自动释放
- `requests.Session` 会随对象销毁而关闭
- SDK 客户端由 Python 垃圾回收机制管理

## 3. 与 Agent 编排的主循环交互模式

### 3.1 交互流程

```
┌─────────────────────────────────────────────────────────────┐
│                    ReactAgent.run()                          │
│                                                               │
│  1. 构建消息历史                                              │
│     messages_to_send = [system_prompt] + conversation_history│
│                                                               │
│  2. 可选：上下文压缩                                          │
│     if should_compress():                                     │
│         messages_to_send = compress(conversation_history)     │
│                                                               │
│  3. 调用 LLM 客户端                                          │
│     raw = client.respond(messages_to_send, temperature)      │
│                                                               │
│  4. 解析响应                                                  │
│     parsed = parse_agent_response(raw)                       │
│                                                               │
│  5. 执行工具或完成任务                                        │
│     if action == "finish":                                   │
│         return final_answer                                   │
│     else:                                                    │
│         observation = tool.execute(action_input)              │
│         conversation_history.append(observation)              │
│                                                               │
│  6. 循环直到完成或达到最大步数                                │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 消息传递格式

**发送给 LLM 的消息**
```python
[
    {"role": "system", "content": "系统提示词..."},
    {"role": "user", "content": "任务：分析代码结构"},
    {"role": "assistant", "content": "思考：我需要先查看项目结构..."},
    {"role": "user", "content": "观察：执行工具 list_directory..."},
    # ... 更多对话轮次
]
```

**从 LLM 接收的响应**
```json
{
  "thought": "我需要先查看项目根目录的文件结构",
  "action": "list_directory",
  "action_input": {"path": "."}
}
```

### 3.3 错误处理

**LLMError 异常**
```python
# dm_agent/clients/base_client.py:9
class LLMError(RuntimeError):
    """当 LLM API 请求失败时抛出。"""
```

**错误传播**
```
LLM API 失败
  └─> LLMError
       └─> Agent 捕获并记录到 observation
            └─> 继续下一轮对话
```

## 4. 架构设计模式

### 4.1 策略模式

**统一接口**
```python
class BaseLLMClient(ABC):
    @abstractmethod
    def complete(self, messages: List[Dict[str, str]], **extra: Any) -> Dict[str, Any]:
        pass

    @abstractmethod
    def extract_text(self, data: Dict[str, Any]) -> str:
        pass
```

**不同实现策略**
- DeepSeek: 使用 `requests.Session` 直接调用 HTTP API
- OpenAI: 使用官方 `openai` SDK
- Claude: 使用官方 `anthropic` SDK
- Gemini: 使用官方 `google.genai` SDK

### 4.2 工厂模式

**创建逻辑**
```python
# dm_agent/clients/llm_factory.py:14
def create_llm_client(provider: str, ...) -> BaseLLMClient:
    if provider == "deepseek":
        return DeepSeekClient(...)
    elif provider == "openai":
        return OpenAIClient(...)
    # ...
```

**默认配置**
```python
PROVIDER_DEFAULTS = {
    "deepseek": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com"},
    "openai": {"model": "gpt-5", "base_url": ""},
    "claude": {"model": "claude-sonnet-4-5", "base_url": ""},
    "gemini": {"model": "gemini-2.5-flash", "base_url": ""},
}
```

### 4.3 适配器模式

**响应格式适配**

DeepSeek 响应：
```python
# 直接从 choices[0].message.content 提取
choices = data.get("choices")
content = choices[0].get("message").get("content")
```

OpenAI 响应：
```python
# 从 SDK 对象提取
response.output_text.strip()
```

Claude 响应：
```python
# 从 SDK 对象的 content 列表提取
for block in response.content:
    if hasattr(block, 'text'):
        text_parts.append(block.text)
```

Gemini 响应：
```python
# 从 SDK 对象提取
response.text.strip()
```

### 4.4 模板方法模式

**respond() 作为模板方法**
```python
def respond(self, messages: List[Dict[str, str]], **extra: Any) -> str:
    # 步骤1：调用抽象方法获取原始响应
    data = self.complete(messages, **extra)
    # 步骤2：调用抽象方法提取文本
    return self.extract_text(data)
```

子类只需实现 `complete()` 和 `extract_text()`。

## 5. 关键特性

### 5.1 消息格式转换

**OpenAI 消息转换**
```python
# dm_agent/clients/openai_client.py:80
def _convert_messages_to_input(self, messages: List[Dict[str, str]]) -> str:
    input_parts = []
    for msg in messages:
        if role == "system":
            input_parts.append(f"System: {content}")
        elif role == "user":
            input_parts.append(f"User: {content}")
        # ...
    return "\n\n".join(input_parts)
```

**Claude 消息分离**
```python
# dm_agent/clients/claude_client.py:48
system_message = None
claude_messages = []
for msg in messages:
    if msg.get("role") == "system":
        system_message = msg.get("content", "")
    else:
        claude_messages.append(msg)
```

### 5.2 错误格式化

**DeepSeek 错误处理**
```python
# dm_agent/clients/deepseek_client.py:100
def _format_error(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = response.text
    message = f"DeepSeek API error: {response.status_code} {response.reason}"
    # 提取详细错误信息
    detail = body.get("error", {}).get("message")
    if detail:
        message = f"{message} - {detail}"
    return message
```

### 5.3 可选依赖处理

**SDK 可用性检查**
```python
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

def __init__(self, ...):
    if not OPENAI_AVAILABLE:
        raise ImportError("openai 未安装。请运行: pip install openai")
```

## 6. 性能考虑

### 6.1 连接复用

**DeepSeek 使用 Session**
```python
self.session = requests.Session()
self.session.headers.update({
    "Authorization": f"Bearer {self.api_key}",
    "Content-Type": "application/json",
})
```

### 6.2 超时控制

**所有客户端支持超时**
```python
timeout: int = 600  # 默认 10 分钟
```

### 6.3 响应解析优化

**DeepSeek 多格式支持**
```python
# 优先检查 output_text
output_text = data.get("output_text")
if output_text:
    return output_text.strip()

# 回退到 choices 格式
choices = data.get("choices")
# ...
```

## 7. 扩展性

### 7.1 添加新提供商

1. 创建新的客户端类继承 `BaseLLMClient`
2. 实现 `complete()` 和 `extract_text()` 方法
3. 在 `llm_factory.py` 中注册

### 7.2 自定义参数

**通过 `**kwargs` 传递**
```python
def create_llm_client(..., **kwargs):
    if provider == "claude":
        if "anthropic_version" in kwargs:
            params["anthropic_version"] = kwargs["anthropic_version"]
```

## 8. 最佳实践

### 8.1 使用工厂创建客户端

```python
from dm_agent.clients import create_llm_client

client = create_llm_client(
    provider="deepseek",
    api_key="your-api-key",
    model="deepseek-chat",
    timeout=300
)
```

### 8.2 错误处理

```python
from dm_agent.clients.base_client import LLMError

try:
    response = client.respond(messages)
except LLMError as e:
    print(f"LLM 调用失败: {e}")
```

### 8.3 温度控制

```python
# 在 Agent 中统一控制温度
raw = self.client.respond(messages_to_send, temperature=self.temperature)
```
