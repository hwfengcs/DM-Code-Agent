"""Explorer Worker - 只读代码探索"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dm_agent.core.multi_agent.messaging.types import AgentRole, SubTask
from dm_agent.core.multi_agent.base import BaseWorkerAgent, WorkerConfig
from dm_agent.tools.base import Tool
from dm_agent.tools import default_tools


class ExplorerWorker(BaseWorkerAgent):
    role = AgentRole.EXPLORER
    
    def __init__(
        self,
        config: Optional[WorkerConfig] = None,
        broker: Optional[Any] = None,
        logger: Optional[Any] = None,
        client: Optional[Any] = None
    ):
        if config is None:
            config = WorkerConfig(role=AgentRole.EXPLORER)
        super().__init__(config, broker, logger)
        self.client = client
    
    def get_tools(self) -> List[Tool]:
        all_tools = default_tools(include_mcp=False, include_rag=False)
        
        readonly_tools = []
        readonly_tool_names = [
            "list_directory",
            "read_file",
            "search_in_file",
            "parse_ast",
            "get_function_signature",
            "find_dependencies",
            "get_code_metrics",
            "task_complete",
        ]
        
        for tool in all_tools:
            if tool.name in readonly_tool_names:
                readonly_tools.append(tool)
        
        return readonly_tools
    
    def execute(self, task: SubTask) -> Dict[str, Any]:
        self._log("TASK_START", f"开始执行探索任务: {task.description[:100]}")
        
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
            
            agent = ReactAgent(
                client=self.client,
                tools=tools,
                max_steps=self.config.max_steps,
                system_prompt=self.get_system_prompt(),
            )
            
            self._log("AGENT_CREATED", "已创建 ReactAgent 实例")
            
            result = agent.run(task.description, max_steps=self.config.max_steps)
            
            self._log(
                "TASK_COMPLETE",
                f"探索任务完成",
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
