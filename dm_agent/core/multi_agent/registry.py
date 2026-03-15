"""Agent 注册表 - 管理 Worker Agent 的创建和工具集"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from dm_agent.core.multi_agent.messaging.types import AgentRole
from dm_agent.core.multi_agent.base import BaseWorkerAgent, WorkerConfig
from dm_agent.core.multi_agent.workers import ExplorerWorker, CoderWorker, TesterWorker
from dm_agent.tools.base import Tool
from dm_agent.tools import default_tools


_worker_classes: Dict[AgentRole, Type[BaseWorkerAgent]] = {
    AgentRole.EXPLORER: ExplorerWorker,
    AgentRole.CODER: CoderWorker,
    AgentRole.TESTER: TesterWorker,
}


def get_tools_for_role(role: AgentRole) -> List[Tool]:
    """获取指定角色可用的工具集"""
    role_tool_configs = {
        AgentRole.EXPLORER: {
            "readonly": True,
            "allowed": [
                "list_directory",
                "read_file",
                "search_in_file",
                "parse_ast",
                "get_function_signature",
                "find_dependencies",
                "get_code_metrics",
                "task_complete",
            ],
        },
        AgentRole.CODER: {
            "readonly": False,
            "allowed": None,
        },
        AgentRole.TESTER: {
            "readonly": False,
            "allowed": [
                "read_file",
                "create_file",
                "edit_file",
                "run_python",
                "run_shell",
                "run_tests",
                "task_complete",
            ],
        },
    }
    
    config = role_tool_configs.get(role, {"readonly": True, "allowed": None})
    all_tools = default_tools(include_mcp=False, include_rag=False)
    
    if config["allowed"] is None:
        return all_tools
    
    filtered_tools = []
    for tool in all_tools:
        if tool.name in config["allowed"]:
            filtered_tools.append(tool)
    
    return filtered_tools


class AgentRegistry:
    """Agent 注册表 - 管理 Worker Agent 的创建"""
    
    def __init__(self):
        self._workers: Dict[str, BaseWorkerAgent] = {}
        self._worker_classes = _worker_classes.copy()
    
    def register_worker_class(self, role: AgentRole, worker_class: Type[BaseWorkerAgent]) -> None:
        """注册新的 Worker 类"""
        self._worker_classes[role] = worker_class
    
    def create_worker(
        self,
        role: AgentRole,
        broker: Optional[Any] = None,
        logger: Optional[Any] = None,
        client: Optional[Any] = None,
        config: Optional[WorkerConfig] = None,
    ) -> BaseWorkerAgent:
        """创建指定角色的 Worker Agent"""
        worker_class = self._worker_classes.get(role)
        
        if worker_class is None:
            raise ValueError(f"未知的 Agent 角色: {role}")
        
        if config is None:
            config = WorkerConfig(role=role)
        
        worker = worker_class(
            config=config,
            broker=broker,
            logger=logger,
            client=client,
        )
        
        self._workers[worker.agent_id] = worker
        
        return worker
    
    def get_worker(self, agent_id: str) -> Optional[BaseWorkerAgent]:
        """根据 ID 获取 Worker"""
        return self._workers.get(agent_id)
    
    def remove_worker(self, agent_id: str) -> None:
        """移除 Worker"""
        if agent_id in self._workers:
            del self._workers[agent_id]
    
    def get_all_workers(self) -> Dict[str, BaseWorkerAgent]:
        """获取所有 Worker"""
        return self._workers.copy()
    
    def get_workers_by_role(self, role: AgentRole) -> List[BaseWorkerAgent]:
        """根据角色获取 Workers"""
        return [w for w in self._workers.values() if w.role == role]
    
    def clear(self) -> None:
        """清空所有 Workers"""
        self._workers.clear()
    
    def get_available_roles(self) -> List[AgentRole]:
        """获取所有可用的角色"""
        return list(self._worker_classes.keys())


__all__ = [
    "AgentRegistry",
    "get_tools_for_role",
]
