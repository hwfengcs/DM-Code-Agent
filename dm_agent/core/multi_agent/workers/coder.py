"""Coder Worker - 代码实现和修改"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dm_agent.core.multi_agent.messaging.types import AgentRole, SubTask
from dm_agent.core.multi_agent.base import BaseWorkerAgent, WorkerConfig
from dm_agent.tools.base import Tool
from dm_agent.tools import default_tools


class CoderWorker(BaseWorkerAgent):
    role = AgentRole.CODER
    
    def __init__(
        self,
        config: Optional[WorkerConfig] = None,
        broker: Optional[Any] = None,
        logger: Optional[Any] = None,
        client: Optional[Any] = None
    ):
        if config is None:
            config = WorkerConfig(role=AgentRole.CODER)
        super().__init__(config, broker, logger)
        self.client = client
    
    def get_tools(self) -> List[Tool]:
        return default_tools(include_mcp=False, include_rag=False)
    
    def execute(self, task: SubTask) -> Dict[str, Any]:
        self._log("TASK_START", f"开始执行编码任务: {task.description[:100]}")
        
        if self.client is None:
            self._log("ERROR", "未配置 LLM 客户端")
            return {
                "task_id": task.task_id,
                "error": "未配置 LLM 客户端",
                "result": None
            }
        
        try:
            from dm_agent.core.agent import ReactAgent
            
            tools = self.get_tools()
            
            enhanced_prompt = self.get_system_prompt()
            if task.context:
                context_str = "\n".join(
                    f"- {k}: {v}" for k, v in task.context.items()
                )
                enhanced_prompt += f"\n\n上下文信息:\n{context_str}"
            
            agent = ReactAgent(
                client=self.client,
                tools=tools,
                max_steps=self.config.max_steps,
                system_prompt=enhanced_prompt,
            )
            
            self._log("AGENT_CREATED", "已创建 ReactAgent 实例")
            
            result = agent.run(task.description, max_steps=self.config.max_steps)
            
            self._log(
                "TASK_COMPLETE",
                f"编码任务完成",
                {"steps": len(result.get("steps", []))}
            )
            
            return {
                "task_id": task.task_id,
                "result": result.get("final_answer", ""),
                "steps": result.get("steps", []),
            }
            
        except Exception as e:
            self._log("ERROR", f"任务执行失败: {str(e)}")
            return {
                "task_id": task.task_id,
                "error": str(e),
                "result": None
            }
