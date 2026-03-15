"""基础类定义"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .messaging.types import AgentRole, SubTask
from ...tools.base import Tool


@dataclass
class WorkerConfig:
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: AgentRole = AgentRole.EXPLORER
    max_steps: int = 50
    timeout: float = 300.0
    tools: List[Tool] = field(default_factory=list)
    system_prompt: Optional[str] = None


class BaseWorkerAgent(ABC):
    role: AgentRole = AgentRole.EXPLORER
    
    def __init__(
        self,
        config: WorkerConfig,
        broker: Optional[Any] = None,
        logger: Optional[Any] = None,
        client: Optional[Any] = None
    ):
        self.config = config
        self.agent_id = config.agent_id
        self.broker = broker
        self.logger = logger
        self.client = client
        self._execution_count = 0
    
    @abstractmethod
    def execute(self, task: SubTask) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_tools(self) -> List[Tool]:
        pass
    
    def get_system_prompt(self) -> str:
        role_prompts = {
            AgentRole.EXPLORER: """你是一个代码探索专家。
你的任务是：
- 搜索和浏览代码库
- 分析代码结构
- 查找特定文件、函数或类
- 理解代码依赖关系

你只能使用只读工具，不能修改任何文件。
完成探索后，请使用 task_complete 工具返回你发现的所有信息。""",
            
            AgentRole.CODER: """你是一个代码实现专家。
你的任务是：
- 编写和修改代码
- 实现新功能
- 修复bug
- 重构代码

你可以使用所有可用工具来完成任务。
完成编码后，请使用 task_complete 工具返回实现摘要。""",
            
            AgentRole.TESTER: """你是一个测试专家。
你的任务是：
- 编写单元测试
- 运行测试套件
- 分析测试覆盖率
- 报告测试结果

你可以使用测试相关工具。
完成测试后，请使用 task_complete 工具返回测试报告。""",
        }
        return self.config.system_prompt or role_prompts.get(self.role, "")
    
    def _log(self, event_type: str, message: str, details: Optional[Dict] = None) -> None:
        if self.logger:
            self.logger.log(
                agent_id=self.agent_id,
                agent_role=self.role.value,
                event_type=event_type,
                message=message,
                details=details or {}
            )
