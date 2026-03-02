# Skill 系统完整指南

## 1. 数据结构

### SkillMetadata（元数据类）

```python
@dataclass
class SkillMetadata:
    name: str  # 唯一标识符
    display_name: str  # 显示名称
    description: str  # 技能描述
    keywords: List[str]  # 匹配关键词
    patterns: List[str]  # 正则匹配模式
    priority: int  # 优先级（越小越高）
    version: str  # 版本号
```

### BaseSkill（抽象基类）

```python
class BaseSkill(ABC):
    @abstractmethod
    def get_metadata(self) -> SkillMetadata:
        """返回技能元数据"""
    
    @abstractmethod
    def get_prompt_addition(self) -> str:
        """返回追加到 system prompt 的文本"""
    
    @abstractmethod
    def get_tools(self) -> List[Tool]:
        """返回该技能提供的专用工具列表"""
    
    def on_activate(self) -> None:
        """技能激活时调用（可选）"""
    
    def on_deactivate(self) -> None:
        """技能停用时调用（可选）"""
```

### ConfigSkill（JSON 配置技能）

```python
class ConfigSkill(BaseSkill):
    def __init__(self, config: Dict[str, Any]) -> None:
        # 从字典初始化
    
    @classmethod
    def from_file(cls, path: str | Path) -> "ConfigSkill":
        # 从 JSON 文件加载
```

## 2. 加载机制

### 内置技能加载（从 `dm_agent/skills/builtin/`）

```python
manager.load_builtin_skills()
# 扫描 builtin 包，导入所有技能类
```

### 自定义技能加载（从 `dm_agent/skills/custom/*.json`）

```python
manager.load_custom_skills()
# 扫描 JSON 文件，使用 ConfigSkill.from_file() 加载
```

### JSON 配置示例

```json
{
  "name": "web_development",
  "display_name": "Web 开发专家",
  "description": "擅长前端框架和 Web 应用开发",
  "keywords": ["react", "vue", "前端", "web"],
  "patterns": ["(react|vue|angular).*component"],
  "priority": 5,
  "prompt_addition": "你是 Web 开发专家，擅长 React、Vue 等框架..."
}
```

## 3. 管理机制

### SkillManager 核心功能

```python
manager = SkillManager(
    max_active_skills=3,  # 最多激活 3 个技能
    min_keyword_score=0.05,  # 最低匹配阈值
    enable_llm_fallback=False,  # 是否启用 LLM 辅助选择
    llm_client=None
)

# 加载所有技能
manager.load_all()

# 查询所有技能信息
info_list = manager.get_all_skill_info()
```

## 4. 自动选择机制

### SkillSelector 选择策略

```python
# 混合评分算法
scores[name] = keyword_score + pattern_score * 1.5

# 1. 关键词匹配（默认）
_keyword_match(task, keywords)  # 返回 0-1 分数

# 2. 正则模式匹配（1.5 倍权重）
_pattern_match(task, patterns)  # 返回 0-1 分数

# 3. LLM 辅助选择（可选，关键词无结果时触发）
_llm_select(task, skills)  # 使用 LLM 选择
```

## 5. 调用流程

```python
# 1. 自动选择技能
skill_names = manager.select_skills_for_task("开发 React 组件")
# 返回：["frontend_dev", "web_development"]

# 2. 激活技能
manager.activate_skills(skill_names)
# 调用每个技能的 on_activate()

# 3. 获取激活技能的内容
prompt_additions = manager.get_active_prompt_additions()
# 返回合并的 prompt 文本

tools = manager.get_active_tools()
# 返回所有激活技能的工具列表

# 4. 停用技能
manager.deactivate_all()
# 调用每个技能的 on_deactivate()
```

## 6. 扩展自定义技能

### 方式一：继承 BaseSkill（Python 类）

```python
class MyCustomSkill(BaseSkill):
    def get_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="my_skill",
            display_name="我的技能",
            description="自定义技能描述",
            keywords=["关键词"],
            priority=10
        )
    
    def get_prompt_addition(self) -> str:
        return "你是某个领域的专家..."
    
    def get_tools(self) -> List[Tool]:
        return [my_custom_tool]
```

### 方式二：JSON 配置文件

```bash
# 创建 dm_agent/skills/custom/my_skill.json
{
  "name": "my_skill",
  "display_name": "我的技能",
  "description": "自定义技能描述",
  "keywords": ["关键词"],
  "prompt_addition": "你是某个领域的专家..."
}
```
