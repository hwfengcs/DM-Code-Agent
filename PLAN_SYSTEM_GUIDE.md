# Plan 系统完整指南

## 1. 数据结构

### PlanStep（计划步骤）

```python
@dataclass
class PlanStep:
    """计划中的单个步骤"""
    
    step_number: int               # 步骤编号
    action: str                    # 工具名称
    reason: str                    # 使用工具的原因
    completed: bool = False        # 是否完成当前步骤
    result: Optional[str] = None   # 返回结果
```

**字段说明**：
- `step_number`：步骤序号，从 1 开始
- `action`：要调用的工具名称（如 `read_file`、`write_file`）
- `reason`：执行此步骤的原因说明
- `completed`：标记步骤是否已完成
- `result`：步骤执行结果（完成后填充）

### TaskPlanner（任务规划器）

```python
class TaskPlanner:
    """任务规划器：在执行前生成全局计划"""
    
    def __init__(self, client: BaseLLMClient, tools: List[Tool]):
        self.client = client
        self.tools = tools
        self.current_plan: List[PlanStep] = []  # 当前计划列表
```

## 2. 计划生成

### plan() - 生成执行计划

```python
def plan(self, task: str) -> List[PlanStep]:
    """
    为任务生成执行计划
    
    Args:
        task: 需要执行的任务描述字符串
        
    Returns:
        包含计划步骤的列表，如果计划生成失败则返回空列表
    """
```

**工作流程**：
1. 构建工具描述列表
2. 向 LLM 发送规划请求
3. 解析 LLM 返回的 JSON 格式计划
4. 创建 `PlanStep` 对象列表

**LLM 提示词结构**：
```
你是一个专业的任务规划助手。请为以下任务生成详细的执行计划。

任务：{task}

可用工具：
- tool1: description1
- tool2: description2

请生成一个结构化的执行计划，包含 3-8 个步骤。

返回 JSON 格式：
{
  "plan": [
    {"step": 1, "action": "工具名称", "reason": "为什么需要这一步"},
    {"step": 2, "action": "工具名称", "reason": "为什么需要这一步"},
    ...
  ]
}
```

**示例输出**：
```python
[
    PlanStep(step_number=1, action="read_file", reason="读取项目结构"),
    PlanStep(step_number=2, action="analyze_code", reason="="分析代码质量"),
    PlanStep(step_number=3, action="task_complete", reason="完成任务")
]
```

### replan() - 重新规划

```python
def replan(
    self, 
    task: str, 
    completed_steps: List[PlanStep], 
    error: Optional[str] = None
) -> List[PlanStep]:
    """
    遇到问题时重新规划
    
    Args:
        task: 原始任务描述
        completed_steps: 已成功完成的步骤列表
        error: 错误信息描述（可选）
        
    Returns:
        新生成的计划步骤列表，如果重新规划失败则返回空列表
    """
```

**使用场景**：
- 某个步骤执行失败
- 发现原计划无法完成任务
- 需要调整执行策略

## 3. 计划执行

### mark_completed() - 标记步骤完成

```python
def mark_completed(self, step_number: int, result: str) -> None:
    """
    标记指定步骤为完成状态
    
    Args:
        step_number: 要标记为完成的步骤编号
        result: 步骤执行的结果描述
    """
```

**示例**：
```python
planner.mark_completed(1, "成功读取文件内容")
```

### get_next_step() - 获取下一步

```python
def get_next_step(self) -> Optional[PlanStep]:
    """
    获取下一个未完成的步骤
    
    Returns:
        下一个未完成的步骤对象，如果没有未完成的步骤则返回 None
    """
```

**示例**：
```python
step = planner.get_next_step()
if step:
    print(f"下一步执行: {step.action}")
else:
    print("所有步骤已完成")
```

### get_progress() - 获取进度报告

```python
def get_progress(self) -> str:
    """
    获取计划执行进度报告
    
    Returns:
        格式化的进度报告字符串
    """
```

**输出示例**：
```
计划进度：2/5 步骤已完成

✓ 步骤 1: read_file - 读取项目结构
   结果：成功读取...
✓ 步骤 2: analyze_code - 分析代码质量
   结果：发现3个问题...
○ 步骤 3: fix_issues - 修复发现的问题
○ 步骤 4: test_fixes - 测试修复效果
○ 步骤 5: task_complete - 完成任务
```

## 4. 计划管理

### has_plan() - 检查是否有计划

```python
def has_plan(self) -> bool:
    """
    检查是否存在活跃的计划
    
    Returns:
        如果存在未完成的计划步骤则返回 True，否则返回 False
    """
```

### clear_plan() - 清空计划

```python
def clear_plan(self) -> None:
    """
    清空当前计划
    
    将当前计划重置为空列表，清除所有已有的计划步骤
    """
```

## 5. 与 ReactAgent 集成

### 初始化规划器

```python
class ReactAgent:
    def __init__(
        self,
        client: BaseLLMClient,
        tools: List[Tool],
        *,
        enable_planning: bool = True,  # 是否启用规划
        ...
    ) -> None:
        self.enable_planning = enable_planning
        self.planner = TaskPlanner(client, tools) if enable_planning else None
```

### 执行流程

```python
def run(self, task: str, *, max_steps: Optional[int] = None) -> Dict[str, Any]:
    # 1. 生成计划（如果启用）
    plan: List[PlanStep] = []
    if self.enable_planning and self.planner:
        plan = self.planner.plan(task)
        if plan:
            plan_text = self.planner.get_progress()
            print(f"\n📋 生成的执行计划：\n{plan_text}")
    
    # 2. 构建 user prompt（包含计划信息）
    task_prompt = self._build_user_prompt(task, steps, plan)
    
    # 3. ReAct 循环执行
    for step_num in range(1, limit + 1):
        # 获取 AI 响应
        raw = self.client.respond(messages_to_send, temperature=self.temperature)
        
        # 解析并执行动作
        parsed = self._parse_agent_response(raw)
        action = parsed.get("action", "").strip()
        
        # 执行工具
        observation = tool.execute(action_input)
        
        # 更新计划进度
        if plan and self.planner:
            for plan_step in plan:
                if plan_step.action == action and not plan_step.completed:
                    self.planner.mark_completed(plan_step.step_number, observation)
                    break
```

### 用户提示词构建

```python
def _build_user_prompt(self, task: str, steps: List[Step], plan: List[PlanStep] = None) -> str:
    lines = [f"任务：{task.strip()}"]
    
    # 如果有计划，添加到提示中
    if plan:
        lines.append("\n执行计划：")
        for plan_step in plan:
            status = "✓" if plan_step.completed else "○"
            lines.append(f"{status} 步骤 {plan_step.step_number}: {plan_step.action} - {plan_step.reason}")
    
    return "\n".join(lines)
```

## 6. 完整执行示例

```python
# 1. 创建 Agent
agent = ReactAgent(client, tools, enable_planning=True)

# 2. 执行任务
result = agent.run("分析项目代码并生成报告")

# 执行流程：
# Step 1: 生成计划
# 📋 生成的执行计划：
# 计划进度：0/4 步骤已完成
# ○ 步骤 1: read_file - 读取项目结构
# ○ 步骤 2: analyze_code - 分析代码质量
# ○ 步骤 3: generate_report - 生成分析报告
# ○ 步骤 4: task_complete - 完成任务

# Step 2: 执行计划中的步骤
# 步骤 1 思考：我需要先读取项目结构
# 步骤 1 动作：read_file
# 步骤 1 观察：成功读取项目结构...

# 计划进度：1/4 步骤已完成
# ✓ 步骤 1: read_file - 读取项目结构
#    结果：成功读取项目结构...
# ○ 步骤 2: analyze_code - 分析代码质量
# ...

# Step 3: 完成所有步骤
# 返回最终结果
```

## 7. 错误处理与回退

### 计划生成失败

```python
try:
    plan = self.planner.plan(task)
    if plan:
        plan_text = self.planner.get_progress()
        print(f"\n{plan_text}")
except Exception as e:
    print(f"⚠️ 计划生成失败：{e}，将使用常规模式执行")
    # 回退到常规 ReAct 模式
```

### 重新规划机制

```python
# 当遇到错误时
completed = [step for step in planner.current_plan if step.completed]
error_msg = "文件不存在: config.json"
new_plan = planner.replan("分析项目配置", completed, error_msg)

if new_plan:
    print(f"重新规划了 {len(new_plan)} 个步骤")
else:
    print("重新规划失败，继续使用原计划")
```

## 8. 最佳实践

### 规划器配置

```python
# 启用规划
agent = ReactAgent(
    client=client,
    tools=tools,
    enable_planning=True,  # 启用规划
    enable_compression=True  # 启用上下文压缩
)
```

### 计划质量优化

1. **工具描述清晰**：确保工具描述准确说明功能
2. **步骤数量合理**：建议 3-8 个步骤，避免过多或过少
3. **逻辑顺序**：步骤应有明确的依赖关系
4. **可验证性**：每个步骤应能独立验证结果

### 与技能系统配合

```python
# 技能系统会自动选择相关技能
# 规划器会基于激活技能的工具生成计划
# 两者协同工作，提高任务执行效率
```
