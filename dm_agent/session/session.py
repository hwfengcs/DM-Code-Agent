"""Session 管理 - 会话和记忆管理核心模块"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .message import Message, MessageList, MessageRole
from .storage import SessionStorage


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_session_id: Optional[str] = None
    title: str = "新会话"
    messages: MessageList = field(default_factory=MessageList)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now().timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_session_id": self.parent_session_id,
            "title": self.title,
            "messages": self.messages.to_dict_list(),
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Session:
        return cls(
            session_id=data.get("session_id", str(uuid.uuid4())[:8]),
            parent_session_id=data.get("parent_session_id"),
            title=data.get("title", "新会话"),
            messages=MessageList.from_dict_list(data.get("messages", [])),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.now().timestamp()),
            updated_at=data.get("updated_at", datetime.now().timestamp()),
        )

    def add_message(self, role: MessageRole, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        msg = Message(role=role, content=content, metadata=metadata or {})
        self.messages.append(msg)
        self.updated_at = datetime.now().timestamp()
        return msg

    def get_messages(self) -> List[Message]:
        return self.messages.get_all()

    def get_message_count(self) -> int:
        return self.messages.count()

    def clear_messages(self) -> None:
        self.messages.clear()
        self.updated_at = datetime.now().timestamp()

    def to_llm_messages(self) -> List[Dict[str, str]]:
        return self.messages.to_llm_format()

    def update_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value
        self.updated_at = datetime.now().timestamp()


class SessionManager:
    """Session 管理器 - 管理多个会话"""

    def __init__(self, storage_dir: str = "dm_agent/data/sessions"):
        self.storage = SessionStorage(storage_dir)
        self._sessions: Dict[str, Session] = {}
        self._load_all_sessions()

    def _load_all_sessions(self) -> None:
        for session in self.storage.get_all_sessions():
            self._sessions[session.session_id] = session

    def create_session(self, title: str = "新会话", parent_id: Optional[str] = None) -> Session:
        session = Session(title=title, parent_session_id=parent_id)
        self._sessions[session.session_id] = session
        self.storage.save_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str, title: str = "新会话") -> Session:
        if session_id in self._sessions:
            return self._sessions[session_id]
        return self.create_session(title=title)

    def save_session(self, session: Session) -> bool:
        session.updated_at = datetime.now().timestamp()
        self._sessions[session.session_id] = session
        return self.storage.save_session(session)

    def delete_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self) -> List[Session]:
        return list(self._sessions.values())

    def get_active_session_count(self) -> int:
        return len(self._sessions)

    def create_child_session(self, parent_id: str, title: str) -> Session:
        return self.create_session(title=title, parent_id=parent_id)

    def get_child_sessions(self, parent_id: str) -> List[Session]:
        return [s for s in self._sessions.values() if s.parent_session_id == parent_id]

    def get_root_sessions(self) -> List[Session]:
        return [s for s in self._sessions.values() if s.parent_session_id is None]

    def clear_all_sessions(self) -> bool:
        self._sessions.clear()
        return self.storage.clear_all()

    def get_storage_stats(self) -> Dict[str, Any]:
        stats = self.storage.get_storage_stats()
        stats["loaded_sessions"] = len(self._sessions)
        return stats
