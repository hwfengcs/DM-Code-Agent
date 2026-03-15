"""消息代理 - 管理 Agent 间通信和日志"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .types import AgentMessage, AgentRole, MessageType, SubTask, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    agent_id: str
    agent_role: str
    event_type: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


class MultiAgentLogger:
    """多 Agent 日志系统"""
    
    def __init__(self, log_dir: str = "dm_agent/log"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "multi_agent.log"
        self.entries: List[LogEntry] = []
    
    def log(
        self,
        agent_id: str,
        agent_role: str,
        event_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        entry = LogEntry(
            timestamp=timestamp,
            agent_id=agent_id,
            agent_role=agent_role,
            event_type=event_type,
            message=message,
            details=details or {}
        )
        self.entries.append(entry)
        self._write_entry(entry)
    
    def _write_entry(self, entry: LogEntry) -> None:
        with open(self.log_file, "a", encoding="utf-8") as f:
            details_str = f" | {entry.details}" if entry.details else ""
            f.write(f"[{entry.timestamp}] [{entry.agent_role}:{entry.agent_id}] "
                   f"[{entry.event_type}] {entry.message}{details_str}\n")
    
    def get_entries(self, agent_id: Optional[str] = None) -> List[LogEntry]:
        if agent_id:
            return [e for e in self.entries if e.agent_id == agent_id]
        return self.entries.copy()
    
    def clear(self) -> None:
        self.entries.clear()


class MessageBroker:
    """消息代理 - 管理 Agent 间通信"""
    
    def __init__(self, logger_instance: Optional[MultiAgentLogger] = None):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._shared_context: Dict[str, Any] = {}
        self._context_history: List[Dict[str, Any]] = []
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._agent_info: Dict[str, AgentRole] = {}
        self.logger = logger_instance or MultiAgentLogger()
    
    def register_agent(self, agent_id: str, role: AgentRole) -> None:
        """注册 Agent"""
        self._queues[agent_id] = asyncio.Queue()
        self._agent_info[agent_id] = role
        self.logger.log(
            agent_id=agent_id,
            agent_role=role.value,
            event_type="REGISTER",
            message="Agent registered"
        )
    
    def unregister_agent(self, agent_id: str) -> None:
        """注销 Agent"""
        if agent_id in self._queues:
            del self._queues[agent_id]
        if agent_id in self._agent_info:
            role = self._agent_info[agent_id]
            del self._agent_info[agent_id]
            self.logger.log(
                agent_id=agent_id,
                agent_role=role.value,
                event_type="UNREGISTER",
                message="Agent unregistered"
            )
    
    async def send(self, message: AgentMessage) -> bool:
        """发送消息到指定 Agent"""
        if message.receiver_id is None:
            return False
        
        receiver_id = message.receiver_id
        if receiver_id not in self._queues:
            self.logger.log(
                agent_id=message.sender_id,
                agent_role=message.sender_role.value,
                event_type="SEND_ERROR",
                message=f"Receiver {receiver_id} not found"
            )
            return False
        
        await self._queues[receiver_id].put(message)
        
        self.logger.log(
            agent_id=message.sender_id,
            agent_role=message.sender_role.value,
            event_type="SEND",
            message=f"Sent {message.message_type.value} to {receiver_id}",
            details={"payload_keys": list(message.payload.keys())}
        )
        return True
    
    async def broadcast(self, message: AgentMessage) -> int:
        """广播消息给所有 Agent（除了发送者）"""
        count = 0
        for agent_id in self._queues:
            if agent_id != message.sender_id:
                msg = AgentMessage(
                    message_id=message.message_id,
                    sender_id=message.sender_id,
                    sender_role=message.sender_role,
                    receiver_id=agent_id,
                    message_type=message.message_type,
                    payload=message.payload.copy(),
                    timestamp=message.timestamp,
                    parent_task_id=message.parent_task_id,
                )
                await self._queues[agent_id].put(msg)
                count += 1
        
        self.logger.log(
            agent_id=message.sender_id,
            agent_role=message.sender_role.value,
            event_type="BROADCAST",
            message=f"Broadcast to {count} agents",
            details={"message_type": message.message_type.value}
        )
        return count
    
    async def receive(
        self,
        agent_id: str,
        timeout: Optional[float] = None
    ) -> Optional[AgentMessage]:
        """接收消息（带超时）"""
        if agent_id not in self._queues:
            return None
        
        try:
            if timeout:
                message = await asyncio.wait_for(
                    self._queues[agent_id].get(),
                    timeout=timeout
                )
            else:
                message = await self._queues[agent_id].get()
            
            role = self._agent_info.get(agent_id, AgentRole.ORCHESTRATOR)
            self.logger.log(
                agent_id=agent_id,
                agent_role=role.value,
                event_type="RECEIVE",
                message=f"Received message from {message.sender_id}",
                details={"message_type": message.message_type.value}
            )
            return message
        except asyncio.TimeoutError:
            return None
    
    def update_shared_context(self, key: str, value: Any, agent_id: str = "") -> None:
        """更新共享上下文"""
        old_value = self._shared_context.get(key)
        self._shared_context[key] = value
        
        snapshot = {
            "timestamp": datetime.now().timestamp(),
            "key": key,
            "old_value": str(old_value)[:100] if old_value else None,
            "new_value": str(value)[:100],
            "updated_by": agent_id
        }
        self._context_history.append(snapshot)
        
        role = self._agent_info.get(agent_id, AgentRole.ORCHESTRATOR)
        self.logger.log(
            agent_id=agent_id,
            agent_role=role.value,
            event_type="CONTEXT_UPDATE",
            message=f"Updated context: {key}",
            details=snapshot
        )
    
    def get_shared_context(self, key: str, default: Any = None) -> Any:
        """获取共享上下文"""
        return self._shared_context.get(key, default)
    
    def get_all_context(self) -> Dict[str, Any]:
        """获取所有共享上下文"""
        return self._shared_context.copy()
    
    def subscribe(self, event_type: str, callback: Callable) -> None:
        """订阅事件"""
        self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """取消订阅事件"""
        if event_type in self._subscribers and callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
    
    async def publish_event(self, event_type: str, data: Dict[str, Any]) -> int:
        """发布事件给所有订阅者"""
        count = 0
        for callback in self._subscribers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
                count += 1
            except Exception as e:
                self.logger.log(
                    agent_id="broker",
                    agent_role="system",
                    event_type="CALLBACK_ERROR",
                    message=f"Event callback failed: {e}",
                    details={"event_type": event_type}
                )
        return count
    
    def get_pending_count(self, agent_id: str) -> int:
        """获取待处理消息数量"""
        if agent_id in self._queues:
            return self._queues[agent_id].qsize()
        return 0
    
    def get_log_entries(self, agent_id: Optional[str] = None) -> List[LogEntry]:
        """获取日志条目"""
        return self.logger.get_entries(agent_id)
    
    def clear(self) -> None:
        """清空所有状态"""
        self._queues.clear()
        self._shared_context.clear()
        self._context_history.clear()
        self._agent_info.clear()
        self.logger.clear()
