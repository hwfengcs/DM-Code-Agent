"""消息数据类 - 管理对话消息"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class MessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    role: MessageRole
    content: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "role": self.role.value,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Message:
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())[:8]),
            role=MessageRole(data.get("role", "user")),
            content=data.get("content", ""),
            created_at=data.get("created_at", datetime.now().timestamp()),
            updated_at=data.get("updated_at", datetime.now().timestamp()),
            metadata=data.get("metadata", {}),
        )

    def to_llm_format(self) -> Dict[str, str]:
        return {
            "role": self.role.value,
            "content": self.content,
        }

    def update_content(self, new_content: str) -> None:
        self.content = new_content
        self.updated_at = datetime.now().timestamp()


class MessageList:
    def __init__(self, messages: Optional[List[Message]] = None):
        self._messages: List[Message] = messages or []

    def add(self, role: MessageRole, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self._messages.append(message)
        return message

    def add_system(self, content: str) -> Message:
        return self.add(MessageRole.SYSTEM, content)

    def add_user(self, content: str) -> Message:
        return self.add(MessageRole.USER, content)

    def add_assistant(self, content: str) -> Message:
        return self.add(MessageRole.ASSISTANT, content)

    def get_all(self) -> List[Message]:
        return self._messages.copy()

    def get_by_role(self, role: MessageRole) -> List[Message]:
        return [m for m in self._messages if m.role == role]

    def get_recent(self, n: int) -> List[Message]:
        return self._messages[-n:] if n > 0 else []

    def to_llm_format(self) -> List[Dict[str, str]]:
        return [m.to_llm_format() for m in self._messages]

    def count(self) -> int:
        return len(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def to_dict_list(self) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self._messages]

    @classmethod
    def from_dict_list(cls, data: List[Dict[str, Any]]) -> MessageList:
        messages = [Message.from_dict(m) for m in data]
        return cls(messages)

    def __len__(self) -> int:
        return len(self._messages)

    def __iter__(self):
        return iter(self._messages)
