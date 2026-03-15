"""Orchestrator - 主调度器，负责任务分解、拓扑排序和并行执行"""

from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dm_agent.core.multi_agent.messaging.types import AgentRole, SubTask, TaskStatus, AgentMessage, MessageType
from dm_agent.core.multi_agent.messaging.broker import MessageBroker, MultiAgentLogger
from dm_agent.core.multi_agent.base import WorkerConfig
from dm_agent.core.multi_agent.registry import AgentRegistry
from dm_agent.core.multi_agent.workers import ExplorerWorker, CoderWorker, TesterWorker
from dm_agent.clients.base_client import BaseLLMClient


class TaskStrategy(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HYBRID = "hybrid"


@dataclass
class DecomposedTask:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    strategy: TaskStrategy = TaskStrategy.PARALLEL
    subtasks: List[SubTask] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "strategy": self.strategy.value,
            "subtasks": [t.to_dict() for t in self.subtasks],
            "created_at": self.created_at,
        }
    
    def get_pending_tasks(self) -> List[SubTask]:
        return [t for t in self.subtasks if t.status == TaskStatus.PENDING]
    
    def get_running_tasks(self) -> List[SubTask]:
        return [t for t in self.subtasks if t.status == TaskStatus.RUNNING]
    
    def get_completed_tasks(self) -> List[SubTask]:
        return [t for t in self.subtasks if t.status == TaskStatus.COMPLETED]
    
    def get_failed_tasks(self) -> List[SubTask]:
        return [t for t in self.subtasks if t.status == TaskStatus.FAILED]
    
    def get_task_by_id(self, task_id: str) -> Optional[SubTask]:
        for t in self.subtasks:
            if t.task_id == task_id:
                return t
        return None


class Orchestrator:
    """主调度器 - 负责任务分解、拓扑排序和并行执行"""
    
    def __init__(
        self,
        client: BaseLLMClient,
        max_workers: int = 3,
        timeout: float = 300.0,
        log_dir: str = "dm_agent/log"
    ):
        self.client = client
        self.agent_id = f"orchestrator_{str(uuid.uuid4())[:8]}"
        self.max_workers = max_workers
        self.timeout = timeout
        
        self.logger = MultiAgentLogger(log_dir)
        self.broker = MessageBroker(self.logger)
        self.registry = AgentRegistry()
        self.worker_pool = ThreadPoolExecutor(max_workers=max_workers)
        
        self._task_history: List[DecomposedTask] = []
        self._shared_context: Dict[str, Any] = {}
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
    
    def _log(self, event_type: str, message: str, details: Optional[Dict] = None) -> None:
        self.logger.log(
            agent_id=self.agent_id,
            agent_role="orchestrator",
            event_type=event_type,
            message=message,
            details=details or {}
        )
    
    def decompose_task(self, task: str) -> DecomposedTask:
        """使用 LLM 分解任务为子任务，并自动分析依赖关系"""
        self._log("DECOMPOSE_START", f"开始分解任务: {task[:100]}...")
        
        decompose_prompt = f"""分析以下任务，将其分解为可并行执行的子任务。

注意：
1. 每个子任务应该使用合适的 agent 类型: explorer, coder, tester
2. 任务描述应该清晰具体
3. 尽量保持子任务数量合理(2-5个)
4. 明确标注子任务之间的依赖关系（dependencies 列表中填写依赖的 task_id）
5. 如果子任务之间没有依赖关系，dependencies 为空数组

返回格式:
{{
  "subtasks": [
    {{
      "task_id": "task_1",
      "description": "具体任务描述",
      "assigned_role": "explorer"|"coder"|"tester",
      "dependencies": [],
      "context": {{}}
    }},
    {{
      "task_id": "task_2",
      "description": "另一个任务描述",
      "assigned_role": "coder",
      "dependencies": ["task_1"],
      "context": {{}}
    }}
  ]
}}

任务: {task}
"""
        
        messages = [{"role": "user", "content": decompose_prompt}]
        response = self.client.respond(messages, temperature=0.3)
        
        try:
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end != -1:
                json_str = response[start:end+1]
                data = json.loads(json_str)
            else:
                data = json.loads(response)
            
            subtasks = []
            for item in data.get("subtasks", []):
                role_str = item.get("assigned_role", "explorer").lower()
                role_map = {
                    "explorer": AgentRole.EXPLORER,
                    "coder": AgentRole.CODER,
                    "tester": AgentRole.TESTER,
                }
                subtasks.append(
                    SubTask(
                        task_id=item.get("task_id", str(uuid.uuid4())[:8]),
                        description=item.get("description", ""),
                        assigned_role=role_map.get(role_str, AgentRole.EXPLORER),
                        dependencies=item.get("dependencies", []),
                        context=item.get("context", {}),
                    )
                )
            
            decomposed = DecomposedTask(
                description=task,
                strategy=TaskStrategy.PARALLEL,
                subtasks=subtasks,
            )
            
            self._log("DECOMPOSE_SUCCESS", f"任务分解完成，生成 {len(subtasks)} 个子任务")
            
            for subtask in subtasks:
                deps_str = f", 依赖: {subtask.dependencies}" if subtask.dependencies else ""
                self._log(
                    "SUBTASK_CREATED",
                    f"子任务 {subtask.task_id}: {subtask.assigned_role.value}{deps_str}",
                    {"description": subtask.description[:80]}
                )
            
            return decomposed
            
        except Exception as e:
            self._log("DECOMPOSE_ERROR", f"任务分解失败: {str(e)}")
            return DecomposedTask(
                description=task,
                strategy=TaskStrategy.PARALLEL,
                subtasks=[
                    SubTask(
                        task_id="explore",
                        description=f"探索和分析: {task}",
                        assigned_role=AgentRole.EXPLORER
                    )
                ]
            )
    
    def _build_dependency_graph(self, decomposed: DecomposedTask) -> Dict[str, Set[str]]:
        """构建依赖图 {task_id: set of dependent task_ids}"""
        graph: Dict[str, Set[str]] = {t.task_id: set() for t in decomposed.subtasks}
        
        for task in decomposed.subtasks:
            for dep_id in task.dependencies:
                if dep_id in graph:
                    graph[dep_id].add(task.task_id)
        
        return graph
    
    def _get_in_degree(self, decomposed: DecomposedTask) -> Dict[str, int]:
        """计算每个任务的入度（依赖数量）"""
        in_degree: Dict[str, int] = {t.task_id: 0 for t in decomposed.subtasks}
        
        for task in decomposed.subtasks:
            in_degree[task.task_id] = len(task.dependencies)
        
        return in_degree
    
    def _topological_sort(self, decomposed: DecomposedTask) -> List[List[str]]:
        """拓扑排序，返回执行层级（每层可并行执行）"""
        in_degree = self._get_in_degree(decomposed)
        graph = self._build_dependency_graph(decomposed)
        
        levels: List[List[str]] = []
        remaining = set(in_degree.keys())
        
        while remaining:
            current_level = [
                task_id for task_id in remaining
                if in_degree[task_id] == 0
            ]
            
            if not current_level:
                self._log("TOPO_CYCLE", "检测到循环依赖，强制处理剩余任务")
                current_level = list(remaining)
            
            levels.append(current_level)
            
            for task_id in current_level:
                remaining.remove(task_id)
                for dependent_id in graph[task_id]:
                    if dependent_id in in_degree:
                        in_degree[dependent_id] -= 1
        
        self._log("TOPO_SORT", f"拓扑排序完成，共 {len(levels)} 层", 
                  {"levels": [[t for t in level] for level in levels]})
        
        return levels
    
    def _execute_single_task(self, task: SubTask) -> Dict[str, Any]:
        """执行单个子任务"""
        self._log(
            "TASK_START",
            f"开始执行子任务 {task.task_id}: {task.description[:100]}..."
        )
        
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now().timestamp()
        
        worker = self.registry.create_worker(
            role=task.assigned_role,
            broker=self.broker,
            logger=self.logger,
            client=self.client,
        )
        
        try:
            result = worker.execute(task)
            
            task.result = result.get("result", "")
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now().timestamp()
            
            self.broker.update_shared_context(
                f"result_{task.task_id}",
                {"result": task.result[:200], "status": "completed"},
                self.agent_id
            )
            
            self._log("TASK_COMPLETE", f"子任务 {task.task_id} 完成")
            
            return result
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now().timestamp()
            
            self._log("TASK_ERROR", f"子任务 {task.task_id} 失败: {str(e)}")
            
            return {
                "task_id": task.task_id,
                "error": str(e),
                "result": None
            }
    
    async def _execute_task_async(self, task: SubTask) -> Dict[str, Any]:
        """异步执行单个子任务"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.worker_pool,
            self._execute_single_task,
            task
        )
    
    async def _execute_level_async(
        self,
        tasks: List[SubTask],
        decomposed: DecomposedTask
    ) -> List[Dict[str, Any]]:
        """并行执行同一层级的任务"""
        self._log(
            "LEVEL_START",
            f"开始并行执行层级任务，共 {len(tasks)} 个",
            {"task_ids": [t.task_id for t in tasks]}
        )
        
        coroutines = [self._execute_task_async(task) for task in tasks]
        results = await asyncio.gather(*coroutines)
        
        completed_ids = [t.task_id for t in tasks if t.status == TaskStatus.COMPLETED]
        
        if self._event_loop:
            asyncio.run_coroutine_threadsafe(
                self.broker.publish_event("TASK_COMPLETED", {
                    "completed_task_ids": completed_ids,
                    "level_size": len(tasks)
                }),
                self._event_loop
            )
        
        self._log(
            "LEVEL_COMPLETE",
            f"层级执行完成",
            {"completed": len(completed_ids), "total": len(tasks)}
        )
        
        return list(results)
    
    def run(self, task: str) -> Dict[str, Any]:
        """运行任务：分解、拓扑排序、按层级并行执行"""
        self._log("RUN_START", f"开始处理任务: {task[:100]}...")
        
        decomposed = self.decompose_task(task)
        self._task_history.append(decomposed)
        
        if not decomposed.subtasks:
            self._log("RUN_ERROR", "任务分解失败，无子任务生成")
            return {
                "task_id": decomposed.task_id,
                "error": "任务分解失败",
                "result": None
            }
        
        levels = self._topological_sort(decomposed)
        
        self._log(
            "EXECUTE_PLAN",
            f"执行计划：共 {len(levels)} 层",
            {"total_subtasks": len(decomposed.subtasks)}
        )
        
        all_results = []
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._event_loop = loop
            
            for level_idx, level_task_ids in enumerate(levels):
                level_tasks = [
                    decomposed.get_task_by_id(tid)
                    for tid in level_task_ids
                    if decomposed.get_task_by_id(tid)
                ]
                
                if not level_tasks:
                    continue
                
                print(f"\n{'='*60}")
                print(f"📦 执行层级 {level_idx + 1}/{len(levels)}: {len(level_tasks)} 个并行任务")
                print(f"   任务: {', '.join([t.task_id for t in level_tasks])}")
                print(f"{'='*60}")
                
                level_results = loop.run_until_complete(
                    self._execute_level_async(level_tasks, decomposed)
                )
                all_results.extend(level_results)
            
        finally:
            if self._event_loop:
                self._event_loop = None
        
        summary = self._aggregate_results(decomposed)
        
        self._log("RUN_COMPLETE", f"任务处理完成")
        
        return {
            "task_id": decomposed.task_id,
            "description": task,
            "subtasks": [t.to_dict() for t in decomposed.subtasks],
            "execution_levels": [[t for t in level] for level in levels],
            "summary": summary,
            "results": all_results,
        }
    
    def run_async(self, task: str) -> Dict[str, Any]:
        """异步运行任务（用于集成到 asyncio 应用）"""
        return asyncio.run(self._run_async_impl(task))
    
    async def _run_async_impl(self, task: str) -> Dict[str, Any]:
        """异步执行的内部实现"""
        self._log("RUN_START", f"开始异步处理任务: {task[:100]}...")
        
        decomposed = self.decompose_task(task)
        self._task_history.append(decomposed)
        
        if not decomposed.subtasks:
            return {
                "task_id": decomposed.task_id,
                "error": "任务分解失败",
                "result": None
            }
        
        levels = self._topological_sort(decomposed)
        all_results = []
        
        for level_idx, level_task_ids in enumerate(levels):
            level_tasks = [
                decomposed.get_task_by_id(tid)
                for tid in level_task_ids
                if decomposed.get_task_by_id(tid)
            ]
            
            if not level_tasks:
                continue
            
            level_results = await self._execute_level_async(level_tasks, decomposed)
            all_results.extend(level_results)
        
        summary = self._aggregate_results(decomposed)
        
        return {
            "task_id": decomposed.task_id,
            "description": task,
            "subtasks": [t.to_dict() for t in decomposed.subtasks],
            "execution_levels": [[t for t in level] for level in levels],
            "summary": summary,
            "results": all_results,
        }
    
    def _aggregate_results(self, decomposed: DecomposedTask) -> str:
        """聚合所有子任务结果"""
        completed = decomposed.get_completed_tasks()
        failed = decomposed.get_failed_tasks()
        
        summary_parts = []
        
        if completed:
            summary_parts.append(f"✅ 已完成 {len(completed)} 个子任务:")
            for task in completed:
                result_preview = task.result[:100] if task.result else "无结果"
                summary_parts.append(f"  - {task.task_id} ({task.assigned_role.value}): {result_preview}...")
        
        if failed:
            summary_parts.append(f"\n❌ 失败 {len(failed)} 个子任务:")
            for task in failed:
                summary_parts.append(f"  - {task.task_id}: {task.error}")
        
        return "\n".join(summary_parts)
    
    def get_logs(self) -> List[Dict[str, Any]]:
        """获取所有日志"""
        return [e.__dict__ for e in self.logger.get_entries()]
    
    def get_task_history(self) -> List[Dict[str, Any]]:
        """获取任务历史"""
        return [t.to_dict() for t in self._task_history]
    
    def shutdown(self) -> None:
        """关闭调度器"""
        self.worker_pool.shutdown(wait=True)
        self._log("SHUTDOWN", "调度器已关闭")
