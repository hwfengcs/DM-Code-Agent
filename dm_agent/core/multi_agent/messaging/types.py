"""消息类型定义"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class MessageType(Enum):
    """消息类型枚举"""
    TASK_ASSIGN = "task_assign"
    TASK_RESULT = "task_result"
    CONTEXT_SHARE = "context_share"
    CONTEXT_REQUEST = "context_request"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    LOG = "log"
    TASK_COMPLETED = "task_completed"
    DEPENDENCY_RESOLVED = "dependency_resolved"


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRole(Enum):
    """Agent 角色类型"""
    ORCHESTRATOR = "orchestrator"
    EXPLORER = "explorer"
    CODER = "coder"
    TESTER = "tester"


@dataclass
class AgentMessage:
    """Agent 间通信消息"""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    sender_id: str = ""
    sender_role: AgentRole = AgentRole.ORCHESTRATOR
    receiver_id: Optional[str] = None
    message_type: MessageType = MessageType.TASK_ASSIGN
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    parent_task_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "sender_role": self.sender_role.value,
            "receiver_id": self.receiver_id,
            "message_type": self.message_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "parent_task_id": self.parent_task_id,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentMessage:
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())[:8]),
            sender_id=data.get("sender_id", ""),
            sender_role=AgentRole(data.get("sender_role", "orchestrator")),
            receiver_id=data.get("receiver_id"),
            message_type=MessageType(data.get("message_type", "task_assign")),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", datetime.now().timestamp()),
            parent_task_id=data.get("parent_task_id"),
            correlation_id=data.get("correlation_id"),
        )


@dataclass
class SubTask:
    """子任务定义"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    assigned_role: AgentRole = AgentRole.EXPLORER
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    parent_task_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "assigned_role": self.assigned_role.value,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "context": self.context,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "parent_task_id": self.parent_task_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SubTask:
        return cls(
            task_id=data.get("task_id", str(uuid.uuid4())[:8]),
            description=data.get("description", ""),
            assigned_role=AgentRole(data.get("assigned_role", "explorer")),
            status=TaskStatus(data.get("status", "pending")),
            dependencies=data.get("dependencies", []),
            context=data.get("context", {}),
            result=data.get("result"),
            error=data.get("error"),
            created_at=data.get("created_at", datetime.now().timestamp()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            parent_task_id=data.get("parent_task_id"),
        )
