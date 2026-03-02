# DM-Code-Agent 架构分析文档

## 一、项目整体架构

```mermaid
graph TB
    subgraph "入口层"
        A[main.py<br/>CLI入口]
    end
    
    subgraph "核心层"
        B[ReactAgent<br/>ReAct智能体]
        C[TaskPlanner<br/>任务规划器]
        D[ContextCompressor<br/>上下文压缩器]
    end
    
    subgraph "客户端层"
        E[BaseLLMClient<br/>抽象基类]
        F[DeepSeekClient]
        G[OpenAIClient]
        H[ClaudeClient]
        I[GeminiClient]
        J[LLMFactory<br/>工厂模式]
    end
    
    subgraph "工具层"
        K[Tool<br/>工具基类]
        L[FileTools<br/>文件操作]
        M[ExecutionTools<br/>代码执行]
        N[CodeAnalysisTools<br/>代码分析]
    end
    
    subgraph "技能系统"
        O[SkillManager<br/>技能管理器]
        P[SkillSelector<br/>技能选择器]
        Q[BaseSkill<br/>技能基类]
        R[BuiltinSkills<br/>内置技能]
    end
    
    subgraph "MCP层"
        S[MCPManager<br/>MCP管理器]
        T[MCPClient<br/>MCP客户端]
        U[MCPConfig<br/>配置管理]
    end
    
    subgraph "提示词层"
        V[SystemPrompts<br/>系统提示词]
        W[CodeAgentPrompt<br/>代码Agent提示词]
    end
    
    A --> B
    A --> O
    A --> S
    B --> C
    B --> D
    B --> E
    B --> K
    B --> O
    J --> F
    J --> G
    J --> H
    J --> I
    O --> P
    O --> Q
    S --> T
    S --> U
```

## 二、模块详细分析

### 1. 入口层

```mermaid
flowchart TD
    Start[程序启动] --> LoadEnv[加载.env环境变量]
    LoadEnv --> ParseArgs[解析命令行参数]
    ParseArgs --> HasTask{有任务参数?}
    HasTask -->|是| SingleTask[run_single_task]
    HasTask -->|否| Interactive{交互模式?}
    Interactive -->|是| InteractiveMode[interactive_mode]
    Interactive -->|否| InteractiveMode
    SingleTask --> InitMCP[初始化MCP管理器]
    InteractiveMode --> InitMCP
    InitMCP --> StartMCP[启动MCP服务器]
    StartMCP --> LoadSkills[加载技能管理器]
    LoadSkills --> CreateAgent[创建ReactAgent]
    CreateAgent --> RunTask[执行任务]
    RunTask --> StopMCP[停止MCP服务器]
    StopMCP --> End[程序结束]
```

### 2. ReactAgent 核心流程

```mermaid
flowchart TD
    Start[agent.run] --> CheckInput{任务非空?}
    CheckInput -->|否| Error[抛出ValueError]
    CheckInput -->|是| SelectSkills[技能自动选择]
    SelectSkills --> EnablePlan{启用规划?}
    EnablePlan -->|是| GeneratePlan[planner.plan生成计划]
    EnablePlan -->|否| BuildPrompt[构建用户提示词]
    GeneratePlan --> BuildPrompt
    BuildPrompt --> AddHistory[添加到对话历史]
    AddHistory --> LoopStart[开始ReAct循环]
    
    LoopStart --> CheckCompress{需要压缩?}
    CheckCompress -->|是| Compress[compressor压缩上下文]
    CheckCompress -->|否| CallLLM
    Compress --> CallLLM[client.respond调用LLM]
    CallLLM --> ParseResponse[_parse_agent_response]
    ParseResponse --> CheckAction{动作类型}
    
    CheckAction -->|finish| FormatAnswer[_format_final_answer]
    CheckAction -->|task_complete| ExecuteTool[tool.execute]
    CheckAction -->|其他工具| ExecuteTool
    CheckAction -->|未知工具| UnknownTool[记录错误]
    
    ExecuteTool --> MarkPlan{有计划?}
    MarkPlan -->|是| UpdatePlan[更新计划进度]
    MarkPlan -->|否| AddHistory2
    UpdatePlan --> AddHistory2[添加到对话历史]
    UnknownTool --> AddHistory2
    
    AddHistory2 --> Callback{有回调?}
    Callback -->|是| InvokeCallback[step_callback]
    Callback -->|否| CheckComplete
    InvokeCallback --> CheckComplete{完成?}
    
    CheckComplete -->|是| ReturnResult[返回结果]
    CheckComplete -->|否| CheckMaxSteps{达到最大步数?}
    CheckMaxSteps -->|是| ReturnLimit[返回限制提示]
    CheckMaxSteps -->|否| LoopStart
```

### 3. TaskPlanner 任务规划器

```mermaid
flowchart TD
    Start[planner.plan] --> BuildToolDesc[构建工具描述]
    BuildToolDesc --> CreatePrompt[创建规划提示词]
    CreatePrompt --> CallLLM[client.respond]
    CallLLM --> ParsePlan[_parse_plan_response]
    ParsePlan --> ParseSuccess{解析成功?}
    ParseSuccess -->|是| CreateSteps[创建PlanStep列表]
    ParseSuccess -->|否| ReturnEmpty[返回空列表]
    CreateSteps --> SavePlan[保存到current_plan]
    SavePlan --> ReturnPlan[返回计划]
    
    ReturnPlan --> Execute[执行阶段]
    Execute --> MarkCompleted[mark_completed]
    MarkCompleted --> GetProgress[get_progress]
    GetProgress --> NeedReplan{需要重新规划?}
    NeedReplan -->|是| Replan[replan重新规划]
    NeedReplan -->|否| Continue
    Replan --> Continue[继续执行]
```

### 4. 技能系统架构

```mermaid
flowchart TD
    subgraph "技能加载"
        A[SkillManager.load_all] --> B[load_builtin_skills]
        A --> C[load_custom_skills]
        B --> D[从builtin包加载]
        C --> E[扫描custom目录JSON]
        D' --> F[注册到skills字典]
        E' --> F
    end
    
    subgraph "技能选择"
        G[select_skills_for_task] --> H[SkillSelector.select]
        H --> I[_score_all计算分数]
        I --> J[_keyword_match关键词匹配]
        I --> K[_pattern_match正则匹配]
        J --> L[综合评分]
        K --> L
        L --> M{分数达标?}
        M -->|否| LLMFallback{启用LLM回退?}
        M -->|是| SortByScore[按分数排序]
        LLMFallback -->|是| _llm_select[LLM辅助选择]
        LLMFallback -->|否| ReturnEmpty
        _llm_select --> SortByScore
        SortByScore --> ReturnTop[返回前N个]
    end
    
    subgraph "技能激活"
        N[activate_skills] --> O[deactivate_all]
        O --> P[遍历选中技能]
        P --> Q[skill.on_activate]
        Q --> R[追加到active_skills]
    end
    
    subgraph "获取技能内容"
        S[get_active_prompt_additions] --> T[合并所有激活技能的prompt]
        U[get_active_tools] --> V[合并所有激活技能的工具]
    end
```

### 5. MCP 管理器架构

```mermaid
flowchart TD
    Start[MCPManager] --> Init[初始化配置]
    Init --> StartAll[start_all]
    StartAll --> GetEnabled[get_enabled_servers]
    GetEnabled --> LoopServers[遍历服务器配置]
    LoopServers --> StartServer[start_server]
    
    StartServer --> CheckRunning{已运行?}
    CheckRunning -->|是| Skip[跳过]
    CheckRunning -->|否| CreateClient[创建MCPClient]
    CreateClient --> ClientStart[client.start]
    ClientStart --> Success{成功?}
    Success -->|是| AddClient[添加到clients字典]
    Success -->|否| Error[记录错误]
    AddClient --> RebuildCache[_rebuild_tools_cache]
    
    RebuildCache --> GetTools[client.get_tools]
    GetTools --> CreateWrapper[_create_tool_wrapper]
    CreateWrapper --> WrapTool[创建Tool包装器]
    WrapTool --> AddCache[添加到_tools_cache]
    
    Skip --> NextServer
    Error --> NextServer
    AddCache --> NextServer{还有服务器?}
    NextServer -->|是| LoopServers
    NextServer -->|否| ReturnCount[返回成功数量]
```

### 6. 上下文压缩器流程

```mermaid
flowchart TD
    Start[ContextCompressor] --> ShouldCompress[should_compress]
    ShouldCompress --> CountUser[统计用户消息数]
    CountUser --> CheckThreshold{达到阈值?}
    CheckThreshold -->|否| ReturnFalse[返回False]
    CheckThreshold -->|是| Compress[compress]
    
    Compress --> Separate[分离系统消息]
    Separate --> KeepRecent[保留最近N轮]
    KeepRecent --> ExtractMiddle[提取中间消息]
    ExtractMiddle --> HasMiddle{有中间消息?}
    HasMiddle -->|否| Combine[直接组合]
    HasMiddle -->|是| ExtractKey[_extract_key_information]
    
    ExtractKey --> ExtractFiles[提取文件路径]
    ExtractKey --> ExtractTools[提取工具调用]
    ExtractKey --> ExtractErrors[提取错误信息]
    ExtractKey --> ExtractCompleted[提取完成操作]
    
    ExtractFiles --> BuildSummary[构建摘要]
    ExtractTools --> BuildSummary
    ExtractErrors --> BuildSummary
    ExtractCompleted --> BuildSummary
    
    BuildSummary --> Combine[组合:系统+摘要+最近]
    Combine --> ResetCount[重置计数器]
    ResetCount --> ReturnCompressed[返回压缩后历史]
```

### 7. 工具系统架构

```mermaid
graph TB
    subgraph "工具基类"
        A[Tool<br/>name, description, runner]
        B[execute]
        C[_require_str<br/>参数验证]
    end
    
    subgraph "文件工具"
        D[list_directory]
        E[read_file]
        F[create_file]
        G[edit_file]
        H[search_in_file]
    end
    
    subgraph "执行工具"
        I[run_python]
        J[run_shell]
        K[run_tests]
        L[run_linter]
    end
    
    subgraph "代码分析工具"
        M[parse_ast]
        N[get_function_signature]
        O[find_dependencies]
        P[get_code_metrics]
    end
    
    subgraph "任务控制"
        Q[task_complete]
    end
    
    A --> B
    B --> C
    default_tools[default_tools] --> D
    default_tools --> E
    default_tools --> F
    default_tools --> G
    default_tools --> H
    default_tools --> I
    default_tools --> J
    default_tools --> K
    default_tools --> L
    default_tools --> M
    default_tools --> N
    default_tools --> O
    default_tools --> P
    default_tools --> Q
```

## 三、数据流图

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Agent
    participant Planner
    participant SkillMgr
    participant LLM
    participant Tools
    participant MCP
    
    User->>CLI: 输入任务
    CLI->>SkillMgr: select_skills_for_task
    SkillMgr-->>CLI: 返回选中技能
    CLI->>Agent: 创建ReactAgent
    Agent->>Planner: plan(task)
    Planner->>LLM: 生成执行计划
    LLM-->>Planner: 返回计划
    Planner-->>Agent: 返回PlanStep列表
    
    loop ReAct循环
        Agent->>LLM: respond(messages)
        LLM-->>Agent: 返回{thought, action, action_input}
        
        alt action == finish
            Agent-->>CLI: 返回最终答案
        else action == task_complete
            Agent->>Tools: execute(action_input)
            Tools-->>Agent: 返回结果
            Agent-->>CLI: 返回结果
        else 其他工具
            alt 工具在MCP
                Agent->>MCP: call_tool
                MCP-->>Agent: 返回结果
            else 内置工具
                Agent->>Tools: execute(action_input)
                Tools-->>Agent: 返回结果
            end
            Agent->>Agent: 添加到对话历史
        end
    end
    
    CLI->>MCP: stop_all
    CLI-->>User: 显示结果
```

## 四、类关系图

```mermaid
classDiagram
    class BaseLLMClient {
        <<abstract>>
        +api_key: str
        +model: str
        +base_url: str
        +timeout: int
        +complete(messages, **extra) Dict
        +extract_text(data) str
        +respond(messages, **extra) str
    }
    
    class DeepSeekClient {
        +complete(messages, **extra) Dict
        +extract_text(data) str
    }
    
    class OpenAIClient {
        +complete(messages, **extra) Dict
        +extract_text(data) str
    }
    
    class ClaudeClient {
        +complete(messages, **extra) Dict
        +extract_text(data) str
    }
    
    class GeminiClient {
        +complete(messages, **extra) Dict
        +extract_text(data) str
    }
    
    class Tool {
        +name: str
        +description: str
        +runner: Callable
        +execute(arguments) str
    }
    
    class Step {
        +thought: str
        +action: str
        +action_input: Any
        +observation: str
        +raw: str
    }
    
    class ReactAgent {
        +client: BaseLLMClient
        +tools: Dict
        +max_steps: int
        +temperature: float
        +conversation_history: List
        +planner: TaskPlanner
        +compressor: ContextCompressor
        +skill_manager: SkillManager
        +run(task, max_steps) Dict
        +reset_conversation() None
    }
    
    class TaskPlanner {
        +client: BaseLLMClient
        +tools: List
        +current_plan: List
        +plan(task) List
        +mark_completed(step_number, result) None
        +get_progress() str
        +replan(task, completed_steps, error) List
    }
    
    class PlanStep {
        +step_number: int
        +action: str
        +reason: str
        +completed: bool
        +result: str
    }
    
    class ContextCompressor {
        +client: BaseLLMClient
        +compress_every: int
        +keep_recent: int
        +turn_count: int
        +should_compress(history) bool
        +compress(history) List
        +get_compression_stats(original, compressed) Dict
    }
    
    class SkillManager {
        +skills: Dict
        +active_skills: List
        +_selector: SkillSelector
        +load_all() int
        +select_skills_for_task(task) List
        +activate_skills(names) None
        +get_active_prompt_additions() str
        +get_active_tools() List
    }
    
    class BaseSkill {
        <<<<abstract>>>>
        +get_metadata() SkillMetadata
        +get_prompt_addition() str
        +get_tools() List
        +on_activate() None
        +on_deactivate() None
    }
    
    class SkillMetadata {
        +name: str
        +display_name: str
        +description: str
        +keywords: List
        +patterns: List
        +priority: int
        +version: str
    }
    
    class MCPManager {
        +config: MCPConfig
        +clients: Dict
        +_tools_cache: List
        +start_all() int
        +start_server(name) bool
        +stop_server(name) None
        +stop_all() None
        +get_tools() List
    }
    
    BaseLLMClient <|-- DeepSeekClient
    BaseLLMClient <|-- OpenAIClient
    BaseLLMClient <|-- ClaudeClient
    BaseLLMClient <|-- GeminiClient
    
    ReactAgent --> BaseLLMClient
    ReactAgent --> Tool
    ReactAgent --> TaskPlanner
    ReactAgent --> ContextCompressor
    ReactAgent --> SkillManager
    
    TaskPlanner --> BaseLLMClient
    TaskPlanner --> Tool
    TaskPlanner --> PlanStep
    
    ContextCompressor --> BaseLLMClient
    
    SkillManager --> BaseSkill
    BaseSkill --> SkillMetadata
    
    MCPManager --> MCPClient
    MCPManager --> Tool
```

## 五、关键设计模式

### 1. 工厂模式
**位置**: `dm_agent/clients/llm_factory.py`

`LLMFactory` 根据提供商名称创建不同的 LLM 客户端实例：
- `deepseek` → `DeepSeekClient`
- `openai` → `OpenAIClient`
- `claude` → `ClaudeClient`
- `gemini` → `GeminiClient`

### 2. 策略模式
**位置**: `dm_agent/skills/selector.py`

`SkillSelector` 使用多种策略选择技能：
- 关键词匹配策略（默认）
- 正则模式匹配策略（高权重）
- LLM 辅助选择策略（可选回退）

### 3. 模板方法模式
**位置**: `dm_agent/clients/base_client.py`

`BaseLLMClient` 定义算法骨架，子类实现具体步骤：
- `complete()`: 抽象方法，子类实现具体 API 调用
- `extract_text()`: 抽象方法，子类实现响应解析
- `respond()`: 模板方法，调用上述两个方法

### 4. 观察者模式
**`step_callback` 回调机制**

`ReactAgent` 通过 `step_callback` 实时通知外部执行状态：
- 在每个步骤执行后调用
- 可用于进度显示、日志记录等

### 5. 装饰器模式
**位置**: `dm_agent/mcp/manager.py`

MCP 工具包装器将外部 MCP 工具封装为内部 `Tool` 对象：
- 统一工具接口
- 透明调用外部工具

### 6. 单例模式
**位置**: `dm_agent/mcp/manager.py`

`MCPManager` 管理多个 MCP 服务器实例：
- 全局唯一的 MCP 管理器
- 统一管理所有 MCP 服务器生命周期

## 六、核心流程总结

### 1. 初始化流程
```
加载环境变量
    ↓
解析命令行参数
    ↓
初始化 MCP 管理器
    ↓
启动 MCP 服务器
    ↓
加载技能管理器
    ↓
创建 ReactAgent
    ↓
执行任务
```

### 2. 任务执行流程
```
技能自动选择
    ↓
生成执行计划（可选）
    ↓
进入 ReAct 循环
    ↓
思考 → 行动 → 观察
    ↓
判断是否完成
    ↓
返回结果
```

### 3. ReAct 循环
```
思考：分析当前状态
    ↓
行动：选择并执行工具
    ↓
观察：获取工具执行结果
    ↓
判断：是否完成任务？
    ↓
继续或结束
```

### 4. 上下文管理
```
每 N 轮对话检查
    ↓
是否需要压缩？
    ↓
提取关键信息：
  - 文件路径
  - 工具调用
  - 错误信息
  - 完成操作
    ↓
构建摘要
    ↓
保留最近 N 轮对话
    ↓
组合：系统消息 + 摘要 + 最近对话
```

### 5. 技能系统
```
加载技能（内置 + 自定义）
    ↓
任务文本分析
    ↓
自动选择相关技能
    ↓
激活选中技能
    ↓
追加技能提示词
    ↓
合并技能工具
    ↓
执行任务
```

### 6. MCP 集成
```
读取 MCP 配置
    ↓
启动启用的服务器
    ↓
获取服务器提供的工具
    ↓
包装为 Tool 对象
    ↓
缓存工具列表
    ↓
统一调用接口
    ↓
停止所有服务器
```

## 七、文件结构说明

```
DM-Code-Agent/
├── main.py                          # CLI 入口点
├── dm_agent/
│   ├── __init__.py
│   ├── core/                        # 核心模块
│   │   ├── agent.py                 # ReactAgent 实现
│   │   └── planner.py               # TaskPlanner 实现
│   ├── clients/                     # LLM 客户端
│   │   ├── base_client.py           # 抽象基类
│   │   ├── llm_factory.py           # 工厂函数
│   │   ├── deepseek_client.py
│   │   ├── openai_client.py
│   │   ├── claude_client.py
│   │   └── gemini_client.py
│   ├── tools/                       # 工具集
│   │   ├── base.py                  # Tool 基类
│   │   ├── file_tools.py            # 文件操作工具
│   │   ├── execution_tools.py       # 代码执行工具
│   │   └── code_analysis_tools.py   # 代码分析工具
│   ├── skills/                      # 技能系统
│   │   ├── base.py                  # BaseSkill 基类
│   │   ├── manager.py               # SkillManager
│   │   ├── selector.py              # SkillSelector
│   │   ├── builtin/                 # 内置技能
│   │   └── custom/                  # 自定义技能
│   ├── mcp/                         # MCP 集成
│   │   ├── manager.py               # MCPManager
│   │   ├── client.py                # MCPClient
│   │   └── config.py                # 配置管理
│   ├── memory/                      # 内存管理
│   │   └── context_compressor.py    # 上下文压缩器
│   └── prompts/                     # 提示词
│       ├── system_prompts.py
│       └── code_agent_prompt.py
├── config.json                      # 配置文件
├── mcp_config.json                  # MCP 配置
└── requirements.txt                 # 依赖列表
```

## 八、扩展指南

### 添加新的 LLM 客户端

1. 继承 `BaseLLMClient`
2. 实现 `complete()` 方法
3. 实现 `extract_text()` 方法
4. 在 `llm_factory.py` 中注册

### 添加新的工具

1. 在 `dm_agent/tools/` 中创建函数
2. 函数签名：`def tool_name(arguments: Dict[str, Any]) -> str`
3. 使用 `_require_str()` 验证参数
4. 在 `default_tools()` 中注册

### 添加新的技能

1. 继承 `BaseSkill` 或使用 `ConfigSkill`
2. 实现 `get_metadata()`、`get_prompt_addition()`、`get_tools()`
3. 放置在 `builtin/` 或 `custom/` 目录

### 添加新的 MCP 服务器

1. 在 `mcp_config.json` 中配置
2. 指定命令、参数、环境变量
3. 自动启动和管理
