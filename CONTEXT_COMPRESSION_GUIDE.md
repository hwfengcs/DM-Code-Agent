# 上下文压缩系统完整指南

## 1. 数据结构

### ContextCompressor（上下文压缩器）

```python
class ContextCompressor:
    """
    每 N 轮对话自动压缩上下文
    
    用于管理长时间对话中的 token 消耗问题。通过定期压缩历史对话记录，
    保持重要的上下文信息同时减少 token 使用量，从而支持更长的对话序列。
    """
    
    def __init__(
        self, 
        client: Optional[BaseLLMClient] = None, 
        compress_every: int = 5, 
        keep_recent: int = 3
    ):
        self.client = client              # LLM 客户端（当前未使用）
        self.compress_every = compress_every  # 每多少轮对话触发一次压缩
        self.keep_recent = keep_recent    # 保留最近的对话轮数
        self.turn_count = 0               # 对话轮数计数器
```

**参数说明**：
- `client`：LLM 客户端（预留用于生成摘要，当前实现未使用）
- `compress_every`：每多少轮对话触发一次压缩（默认 5 轮）
- `keep_recent`：保留最近的最近对话轮数（默认 3 轮）

### 对话历史结构

```python
history: List[Dict[str, str]] = [
    {"role": "system", "content": "系统提示词"},
    {"role": "user", "content": "用户消息"},
    {"role": "assistant", "content": "助手响应"},
    ...
]
```

## 2. 压缩时机管理

### should_compress() - 判断是否需要压缩

```python
def should_compress(self, history: List[Dict[str, str]]) -> bool:
    """
    判断是否需要压缩对话历史
    
    通过统计用户消息数量来确定当前对话轮数，当达到设定阈值时返回 True
    
    Args:
        history: 对话历史列表
        
    Returns:
        当对话轮数达到压缩阈值时返回 True，否则返回 False
    """
```

**工作原理**：
1. 统计用户消息数量（每个用户消息代表一轮对话）
2. 更新内部计数器 `turn_count`
3. 判断是否达到 `compress_every` 阈值

**示例**：
```python
compressor = ContextCompressor(compress_every=3)

history = [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！"},
    {"role": "user", "content": "分析项目"}
]

# 2 轮对话，未达到阈值
compressor.should_compress(history)  # False

history.append({"role": "assistant", "content": "正在分析..."})
history.append({"role": "user", "content": "继续"})

# 3 轮对话，达到阈值
compressor.should_compress(history)  # True
```

## 3. 压缩执行

### compress() - 执行压缩

```python
def compress(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    压缩对话历史
    
    采用提取关键信息的策略，保留最近 N 轮对话，将之前的对话历史压缩为摘要信息
    
    Args:
        history: 原始对话历史列表
        
    Returns:
        压缩后的对话历史列表
    """
```

**压缩策略**：
1. 分离系统消息和其他消息
2. 保留最近 `keep_recent` 轮对话（`keep_recent * 2` 条消息）
3. 将中间消息压缩为关键信息摘要
4. 组合：系统消息 + 压缩摘要 + 最近消息

**压缩前后对比**：

```python
# 压缩前（假设 keep_recent=1）
[
    {"role": "system", "content": "系统提示"},
    {"role": "user", "content": "任务1"},
    {"role": "assistant", "content": "执行中..."},
    {"role": "user", "content": "任务2"},
    {"role": "assistant", "content": "完成"},
    {"role": "user", "content": "任务3"},
    {"role": "assistant", "content": "结果"}
]

# 压缩后
[
    {"role": "system", "content": "系统提示"},
    {"role": "user", "content": "历史对话摘要：\n涉及文件：main.py\n使用的工具：read_file"},
    {"role": "user", "content": "任务3"},
    {"role": "assistant", "content": "结果"}
]
```

## 4. 关键信息提取

### _extract_key_information() - 提取关键信息

```python
def _extract_key_information(self, messages: List[Dict[str, str]]) -> str:
    """
    提取式摘要：从对话历史中提取关键信息
    
    通过正则表达式识别和提取对话中的关键信息，包括：
    - 文件路径
    - 工具调用
    - 错误信息
    - 完成的任务
    
    Args:
        messages: 需要提取信息的对话消息列表
        
    Returns:
        格式化的关键信息摘要字符串
    """
```

**提取规则**：

1. **文件路径提取**
```python
# 匹配模式
r"(?:path|文件|读取|创建|编辑)[:：]\s*([^\s,，;；\n]+\.[a-zA-Z]+)"

# 示例提取
"读取文件：main.py" → "main.py"
"创建新文件 test.py" → "test.py"
```

2. **工具调用提取**
```python
# 匹配模式
r"执行工具\s+(\w+)"

# 示例提取
"执行工具 read_file，输入：..." → "read_file"
"执行工具 write_file，输入：..." → "write_file"
```

3. **错误信息提取**
```python
# 匹配关键词
["错误", "error", "Error", "失败", "异常"]

# 示例提取
"执行失败：文件不存在" → "执行失败：文件不存在"
"Error: Permission denied" → "Error: Permission denied"
```

4. **完成的任务提取**
```python
# 匹配关键词
["完成", "成功"]

# 示例提取
"成功读取文件" → "成功读取文件"
"任务已完成" → "任务已完成"
```

**输出示例**：
```
涉及文件：main.py, utils.py, config.json
使用的工具：read_file, write_file, analyze_code
遇到的错误：
执行失败：文件不存在
已完成的操作：
成功读取文件
任务已完成
```

## 5. 压缩统计

### get_compression_stats() - 获取压缩统计

```python
def get_compression_stats(
    self, 
    original: List[Dict[str, str]], 
    compressed: List[Dict[str, str]]
) -> Dict[str, Any]:
    """
    获取压缩统计信息
    
    计算并返回压缩前后的统计信息
    
    Args:
        original: 原始对话历史
        compressed: 压缩后的对话历史
        
    Returns:
        包含压缩统计信息的字典：
        - original_messages: 原始消息数量
        - compressed_messages: 压缩后消息数量
        - compression_ratio: 压缩率 (0-1 之间)
        - saved_messages: 节省的消息数量
    """
```

**统计示例**：
```python
original = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
]

compressed = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "历史对话摘要：..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
]

stats = compressor.get_compression_stats(original, compressed)

# 输出
{
    "original_messages": 7,
    "compressed_messages": 4,
    "compression_ratio": 0.4286,  # 42.86% 压缩率
    "saved_messages": 3
}
```

## 6. 与 ReactAgent 集成

### 初始化压缩器

```python
class ReactAgent:
    def __init__(
        self,
        client: BaseLLMClient,
        tools: List[Tool],
        *,
        enable_compression: bool = True,  # 是否启用上下文压缩
        ...
    ) -> None:
        self.enable_compression = enable_compression
        self.compressor = ContextCompressor(
            client, 
            compress_every=5,  # 每 5 轮压缩一次
            keep_recent=3      # 保留最近 3 轮
        ) if enable_compression else None
```

### 执行流程

```python
def run(self, task: str, *, max_steps: Optional[int] = None) -> Dict[str, Any]:
    for step_num in range(1, limit + 1):
        # 1. 检查是否需要压缩
        messages_to_send = [
            {"role": "system", "content": self.system_prompt}
        ] + self.conversation_history
        
        if self.enable_compression and self.compressor:
            if self.compressor.should_compress(self.conversation_history):
                print(f"\n🗜️ 压缩对话历史以节省 token...")
                
                # 2. 执行压缩
                compressed_history = self.compressor.compress(
                    self.conversation_history
                )
                
                # 3. 使用压缩后的历史
                messages_to_send = [
                    {"role": "system", "content": self.system_prompt}
                ] + compressed_history
                
                # 4. 显示压缩统计
                stats = self.compressor.get_compression_stats(
                    self.conversation_history, 
                    compressed_history
                )
                print(
                    f"   压缩率：{stats['compression_ratio']:.1%}，"
                    f"节省 {stats['saved_messages']} 条消息"
                )
        
        # 5. 获取 AI 响应
        raw = self.client.respond(messages_to_send, temperature=self.temperature)
```

## 7. 完整执行示例

```python
# 1. 创建 Agent（启用压缩）
agent = ReactAgent(
    client=client,
    tools=tools,
    enable_compression=True
)

# 2. 执行长任务
result = agent.run("分析整个项目并生成详细报告")

# 执行过程：
# 第 1-4 轮：正常执行，不压缩
# 第 5 轮：
# 🗜️ 压缩对话历史以节省 token...
#    压缩率：42.9%，节省 3 条消息
# 
# 历史对话摘要：
# 涉及文件：main.py, utils.py, config.json
# 使用的工具：read_file, analyze_code
# 已完成的操作：
# 成功读取文件
# 任务已完成

# 第 6-9 轮：正常执行，不压缩
# 第 10 轮：再次压缩
```

## 8. 压缩策略分析

### 策略优势

1. **保持上下文连贯性**：保留最近对话，确保理解当前任务
2. **减少 token 消耗**：压缩早期对话，节省 API 成本
3. **保留关键信息**：提取文件、工具、错误等重要信息
4. **自动触发**：无需手动干预，根据对话轮数自动判断

### 适用场景

**适合压缩**：
- 长时间运行的任务（如代码分析、批量处理）
- 多轮对话（如逐步调试、迭代开发）
- 大型项目分析（需要读取多个文件）

**不适合压缩**：
- 短任务（单轮对话即可完成）
- 需要精确历史上下文的任务
- 实时交互式对话

## 9. 配置建议

### 不同场景的参数配置

```python
# 场景 1：大型项目分析（激进压缩）
compressor = ContextCompressor(
    compress_every=3,  # 每 3 轮压缩
    keep_recent=2      # 保留最近 2 轮
)

# 场景 2：常规任务（平衡配置）
compressor = ContextCompressor(
    compress_every=5,  # 每 5 轮压缩
    keep_recent=3      # 保留最近 3 轮
)

# 场景 3：精确上下文（保守压缩）
compressor = ContextCompressor(
    compress_every=10, # 每 10 轮压缩
    keep_recent=5      # 保留最近 5 轮
)

# 场景 4：禁用压缩
compressor = None  # 或 enable_compression=False
```

## 10. 扩展与优化

### 扩展建议

1. **使用 LLM 生成摘要**
```python
def _llm_summary(self, messages: List[Dict[str, str]]) -> str:
    """使用 LLM 生成更智能的摘要"""
    prompt = f"请总结以下对话的关键信息：\n{messages}"
    response = self.client.respond([{"role": "user", "content": prompt}])
    return response
```

2. **基于 token 数量触发**
```python
def should_compress_by_tokens(self, history: List[Dict[str, str]], max_tokens: int = 4000) -> bool:
    """根据 token 数量判断是否需要压缩"""
    total_tokens = sum(len(msg["content"]) for msg in history)
    return total_tokens > max_tokens
```

3. **保留重要对话**
```python
def _is_important_message(self, message: Dict[str, str]) -> bool:
    """判断消息是否重要（如包含错误、关键决策等）"""
    content = message.get("content", "")
    return any(kw in content for kw in ["错误", "重要", "关键", "失败"])
```

## 11. 最佳实践

### 使用建议

1. **合理设置压缩阈值**：根据任务复杂度调整 `compress_every`
2. **保留足够的最近对话**：`keep_recent` 至少为 2-3 轮
3. **监控压缩效果**：使用 `get_compression_stats` 查看压缩率
4. **结合任务规划**：压缩与规划系统配合，提高效率
5. **测试不同配置**：根据实际效果调整参数

### 性能优化

```python
# 在长任务中启用压缩
agent = ReactAgent(
    client=client,
    tools=tools,
    enable_compression=True,
    enable_planning=True  # 配合规划器使用
)

# 短任务禁用压缩
agent = ReactAgent(
    client=client,
    tools=tools,
    enable_compression=False  # 短任务不需要
)
```
